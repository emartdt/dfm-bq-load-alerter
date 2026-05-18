from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from google.cloud import bigquery

from dfm_bq_load_alerter.bq.client import get_client
from dfm_bq_load_alerter.bq.templating import (
    ConditionQueryTemplateError,
    render_condition_query,
)

log = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")


class ConditionQueryError(ValueError):
    """Raised when a user-supplied row_count query is invalid or unsafe."""


# DML/DDL keywords that must never appear as the first significant token of a
# user-supplied row_count query. We only accept SELECT/WITH read-only queries.
_FORBIDDEN_KEYWORDS = frozenset(
    {
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "CREATE",
        "ALTER",
        "TRUNCATE",
        "MERGE",
        "GRANT",
        "REVOKE",
        "CALL",
        "EXECUTE",
        "EXPORT",
        "LOAD",
    }
)


_COMMENT_LINE_RE = re.compile(r"--[^\n]*")
_COMMENT_BLOCK_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_FIRST_TOKEN_RE = re.compile(r"^\s*([A-Za-z_]+)")
_WORD_RE = re.compile(r"\b([A-Za-z_]+)\b")


@dataclass(frozen=True, slots=True)
class TableMetadata:
    dataset: str
    table_name: str
    last_modified: datetime | None
    row_count: int | None
    used_count_fallback: bool
    streaming_recent_rows: int | None = None


def _strip_sql_comments(query: str) -> str:
    """Remove `--` line comments and `/* ... */` block comments."""
    no_block = _COMMENT_BLOCK_RE.sub(" ", query)
    return _COMMENT_LINE_RE.sub(" ", no_block)


def _validate_condition_query(query: str) -> str:
    """Reject anything that isn't a read-only SELECT/WITH query.

    The check is intentionally conservative: we strip comments, require the
    first significant token to be SELECT or WITH (case-insensitive), and refuse
    when any DML/DDL keyword appears as a standalone word elsewhere in the
    query. BigQuery's parser is the final source of truth — this guard is
    defence-in-depth so a misconfigured row never enqueues a destructive
    statement.
    """
    stripped = _strip_sql_comments(query).strip()
    if not stripped:
        raise ConditionQueryError("condition_query 가 비어 있습니다.")
    first = _FIRST_TOKEN_RE.match(stripped)
    if first is None:
        raise ConditionQueryError("condition_query 의 시작 토큰을 찾을 수 없습니다.")
    head = first.group(1).upper()
    if head not in {"SELECT", "WITH"}:
        raise ConditionQueryError(
            f"condition_query 는 SELECT 또는 WITH 로 시작해야 합니다 (got {head})."
        )
    for match in _WORD_RE.finditer(stripped):
        token = match.group(1).upper()
        if token in _FORBIDDEN_KEYWORDS:
            raise ConditionQueryError(
                f"condition_query 에 금지된 키워드가 포함되어 있습니다: {token}"
            )
    return stripped


def _query_metadata(
    client: bigquery.Client, dataset: str, table_name: str
) -> tuple[datetime | None, int | None]:
    """Read last_modified_time and row_count from `__TABLES__` (project-scoped).

    `__TABLES__` is the canonical low-cost source for metadata that load jobs
    update. It returns msec since epoch for last_modified_time. We avoid
    INFORMATION_SCHEMA.PARTITIONS here because it requires the table to be
    partitioned and adds a join cost — `__TABLES__` is uniformly available.
    """
    query = (
        f"SELECT TIMESTAMP_MILLIS(last_modified_time) AS last_modified, row_count "
        f"FROM `{client.project}.{dataset}.__TABLES__` "
        f"WHERE table_id = @table_name"
    )
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("table_name", "STRING", table_name)
        ],
        use_legacy_sql=False,
    )
    rows = list(client.query(query, job_config=job_config).result())
    if not rows:
        return None, None
    row = rows[0]
    last_modified = row["last_modified"]
    row_count = int(row["row_count"]) if row["row_count"] is not None else None
    return last_modified, row_count


def _query_streaming_recent_rows(
    client: bigquery.Client, dataset: str, table_name: str
) -> int | None:
    """Read recent streaming insert rows (last 1h) from STREAMING_TIMELINE_BY_PROJECT.

    INFORMATION_SCHEMA.PARTITIONS / __TABLES__ does NOT reflect streaming
    buffer contents until rows are committed to columnar storage (R9). This
    query inspects the streaming buffer directly. Returns None if the table
    is not streamed or the view is unavailable.
    """
    query = (
        "SELECT SUM(total_rows) AS rows "
        f"FROM `{client.project}.region-asia-northeast3`."
        "INFORMATION_SCHEMA.STREAMING_TIMELINE_BY_PROJECT "
        "WHERE start_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR) "
        "AND ref_table_name = @table_name "
        "AND ref_table_dataset_id = @dataset"
    )
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("table_name", "STRING", table_name),
            bigquery.ScalarQueryParameter("dataset", "STRING", dataset),
        ],
        use_legacy_sql=False,
    )
    try:
        rows = list(client.query(query, job_config=job_config).result())
    except Exception as exc:  # noqa: BLE001 — streaming view may be unavailable
        log.debug("streaming timeline unavailable for %s.%s: %s", dataset, table_name, exc)
        return None
    if not rows or rows[0]["rows"] is None:
        return None
    return int(rows[0]["rows"])


def _count_rows(client: bigquery.Client, dataset: str, table_name: str) -> int:
    query = f"SELECT COUNT(*) AS n FROM `{client.project}.{dataset}.{table_name}`"
    rows = list(client.query(query, use_legacy_sql=False).result())
    return int(rows[0]["n"])


def _extract_scalar_int(row: object) -> int:
    """Pull the first column of a one-row BigQuery result as an integer.

    The user query contract is "one row, one integer column". We always read
    position 0 (BigQuery ``Row`` supports both name and ordinal indexing).
    """
    try:
        value = row[0]  # type: ignore[index]
    except Exception as exc:
        raise ConditionQueryError(
            "condition_query 결과에서 첫 컬럼 값을 읽을 수 없습니다."
        ) from exc
    if value is None:
        raise ConditionQueryError(
            "condition_query 결과가 NULL 입니다 (정수 row count 필요)."
        )
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ConditionQueryError(
            f"condition_query 결과를 정수로 변환할 수 없습니다: {value!r}"
        ) from exc


def render_and_validate_condition_query(query: str) -> str:
    """Render Jinja2 template (KST now) and run the static validator.

    Returns the rendered, sanitized SQL ready for BigQuery.
    Raises ``ConditionQueryError`` for template or validation failures.
    """
    try:
        rendered = render_condition_query(query)
    except ConditionQueryTemplateError as exc:
        raise ConditionQueryError(str(exc)) from exc
    return _validate_condition_query(rendered)


def run_condition_query(
    client: bigquery.Client,
    *,
    query: str,
    max_bytes: int,
) -> tuple[int, int | None]:
    """Render template, validate, dry-run, and execute a user row_count query.

    Returns ``(row_count, bytes_processed)``. ``bytes_processed`` may be None
    if the BigQuery client does not surface the value (e.g. mocked tests).

    Raises ``ConditionQueryError`` for template/validation/budget failures.
    """
    sanitized = render_and_validate_condition_query(query)

    dry_config = bigquery.QueryJobConfig(use_legacy_sql=False, dry_run=True, use_query_cache=False)
    dry_job = client.query(sanitized, job_config=dry_config)
    estimated = getattr(dry_job, "total_bytes_processed", None)
    if estimated is not None and estimated > max_bytes:
        raise ConditionQueryError(
            f"condition_query 처리량 {estimated} bytes 가 상한 {max_bytes} bytes 를 초과했습니다."
        )

    exec_config = bigquery.QueryJobConfig(use_legacy_sql=False)
    job = client.query(sanitized, job_config=exec_config)
    rows = list(job.result())
    if not rows:
        raise ConditionQueryError("condition_query 결과가 비어 있습니다 (정확히 1행 필요).")
    row_count = _extract_scalar_int(rows[0])
    bytes_processed = getattr(job, "total_bytes_processed", None)
    return row_count, bytes_processed


def fetch_metadata(
    dataset: str,
    table_name: str,
    *,
    project_id: str | None = None,
    client: bigquery.Client | None = None,
    force_count: bool = False,
    row_count_query: str | None = None,
    row_count_query_max_bytes: int = 104857600,
) -> TableMetadata:
    """Fetch monitoring metadata for a single BigQuery table.

    `project_id` 가 주어지면 그 프로젝트의 클라이언트를 사용 (테이블별 라우팅).
    `client` 가 명시되면 우선. 둘 다 None 이면 settings.bq_project_id 폴백.

    Strategy:
    1. Read __TABLES__ for last_modified + row_count (low-cost metadata).
    2. If ``row_count_query`` is provided, run it (with byte budget) and use
       its result as ``row_count`` instead of the __TABLES__ value or COUNT(*).
       last_modified always comes from __TABLES__ — the custom query owns the
       row_count semantics only.
    3. Otherwise: if row_count is None or `force_count` is True, run COUNT(*)
       (fallback — recorded in bq_query_log by the caller for cost monitoring).
    4. Read STREAMING_TIMELINE for recent buffer rows; combine when streaming
       is active. Skipped when a custom row_count_query is supplied because the
       user query is assumed to be authoritative for the count.
    """
    bq = client or get_client(project_id)
    last_modified, row_count = _query_metadata(bq, dataset, table_name)
    used_count_fallback = False
    streaming_recent: int | None = None

    if row_count_query is not None:
        row_count, _bytes = run_condition_query(
            bq, query=row_count_query, max_bytes=row_count_query_max_bytes
        )
    else:
        if row_count is None or force_count:
            row_count = _count_rows(bq, dataset, table_name)
            used_count_fallback = True

        streaming_recent = _query_streaming_recent_rows(bq, dataset, table_name)
        if streaming_recent is not None and streaming_recent > 0:
            # streaming buffer rows are not yet in __TABLES__; reflect them.
            if row_count is not None:
                row_count = row_count + streaming_recent
            if last_modified is None:
                last_modified = datetime.now(tz=KST)

    return TableMetadata(
        dataset=dataset,
        table_name=table_name,
        last_modified=last_modified,
        row_count=row_count,
        used_count_fallback=used_count_fallback,
        streaming_recent_rows=streaming_recent,
    )
