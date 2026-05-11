from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from google.cloud import bigquery

from dfm_bq_load_alerter.bq.client import get_client

log = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")


@dataclass(frozen=True, slots=True)
class TableMetadata:
    dataset: str
    table_name: str
    last_modified: datetime | None
    row_count: int | None
    used_count_fallback: bool
    streaming_recent_rows: int | None = None


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


def fetch_metadata(
    dataset: str,
    table_name: str,
    *,
    project_id: str | None = None,
    client: bigquery.Client | None = None,
    force_count: bool = False,
) -> TableMetadata:
    """Fetch monitoring metadata for a single BigQuery table.

    `project_id` 가 주어지면 그 프로젝트의 클라이언트를 사용 (테이블별 라우팅).
    `client` 가 명시되면 우선. 둘 다 None 이면 settings.bq_project_id 폴백.

    Strategy:
    1. Read __TABLES__ for last_modified + row_count (low-cost metadata).
    2. If row_count is None or `force_count` is True, run COUNT(*) (fallback
       — recorded in bq_query_log by the caller for cost monitoring).
    3. Read STREAMING_TIMELINE for recent buffer rows; combine if streaming
       is active.
    """
    bq = client or get_client(project_id)
    last_modified, row_count = _query_metadata(bq, dataset, table_name)
    used_count_fallback = False

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
