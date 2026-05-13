"""Fetch the last N jobs that wrote to each given BigQuery table.

Edit ``TABLES`` / ``LIMIT`` / ``JOB_TYPES`` below from your IDE, then run:

    python scripts/bigquery/recent_loads.py

Covers LOAD jobs, DML/CTAS via QUERY jobs (INSERT/MERGE/UPDATE/CREATE...AS),
and COPY jobs. Streaming inserts / Storage Write API writes do NOT appear in
JOBS_* — `__TABLES__.last_modified_time` may move without any row here.

Auth: Application Default Credentials. For tables loaded by other SAs (BQ DTS,
Airflow, etc.) you need `bigquery.jobs.listAll` on the project — otherwise
those jobs are invisible to you even though the table was modified.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from google.cloud import bigquery


TABLES: list[str] = [
    "emart-datafabric.bw.PZDATE",
    "emart-datafabric.bw.ZMM_AD701",
    "emart-datafabric.bw.ZSD_MG500",
    "smart-ruler-304409.cds_core.TB_BAIN_MEMBR_GRADE",
    "smart-ruler-304409.cds_core.TB_DW_POS_EVENT_RESULT",
    "smart-ruler-304409.cds_core.TB_DW_STR_PRDT",
    "smart-ruler-304409.elt_verify.ELT_VERIFY_LOG",
]

LIMIT: int = 10

LOOKBACK_DAYS: int = 90

JOB_TYPES: tuple[str, ...] = ("LOAD", "QUERY", "COPY")

WRITE_STATEMENT_TYPES: tuple[str, ...] = (
    "INSERT",
    "MERGE",
    "UPDATE",
    "DELETE",
    "TRUNCATE_TABLE",
    "CREATE_TABLE_AS_SELECT",
    "CREATE_OR_REPLACE_TABLE_AS_SELECT",
    "CREATE_VIEW",
    "CREATE_OR_REPLACE_VIEW",
)

REGION_BY_PROJECT: dict[str, str] = {
    "emart-datafabric": "region-asia-northeast3",
    "smart-ruler-304409": "region-asia-northeast3",
}

DEFAULT_REGION = "region-asia-northeast3"


@dataclass(frozen=True, slots=True)
class TableRef:
    project: str
    dataset: str
    table: str

    @classmethod
    def parse(cls, fqn: str) -> "TableRef":
        parts = fqn.split(".")
        if len(parts) != 3:
            raise ValueError(f"Expected project.dataset.table, got: {fqn!r}")
        return cls(*parts)

    def fqn(self) -> str:
        return f"{self.project}.{self.dataset}.{self.table}"


def fetch_recent_loads(
    project: str,
    region: str,
    tables: list[TableRef],
    limit: int,
    lookback_days: int,
) -> dict[str, list[bigquery.Row]]:
    client = bigquery.Client(project=project)

    query = f"""
    WITH ranked AS (
      SELECT
        destination_table.dataset_id AS dataset_id,
        destination_table.table_id   AS table_id,
        creation_time,
        start_time,
        end_time,
        TIMESTAMP_DIFF(end_time, start_time, SECOND) AS duration_sec,
        job_type,
        statement_type,
        state,
        user_email,
        total_bytes_processed,
        error_result.reason AS error_reason,
        ROW_NUMBER() OVER (
          PARTITION BY destination_table.dataset_id, destination_table.table_id
          ORDER BY creation_time DESC
        ) AS rn
      FROM `{region}`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
      WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @lookback_days DAY)
        AND job_type IN UNNEST(@job_types)
        AND (
          job_type IN ('LOAD', 'COPY')
          OR (job_type = 'QUERY' AND statement_type IN UNNEST(@write_stmt_types))
        )
        AND destination_table.project_id = @project
        AND CONCAT(destination_table.dataset_id, '.', destination_table.table_id)
            IN UNNEST(@table_keys)
    )
    SELECT *
    FROM ranked
    WHERE rn <= @limit
    ORDER BY dataset_id, table_id, creation_time DESC
    """

    table_keys = [f"{t.dataset}.{t.table}" for t in tables]
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("project", "STRING", project),
            bigquery.ScalarQueryParameter("limit", "INT64", limit),
            bigquery.ScalarQueryParameter("lookback_days", "INT64", lookback_days),
            bigquery.ArrayQueryParameter("table_keys", "STRING", table_keys),
            bigquery.ArrayQueryParameter("job_types", "STRING", list(JOB_TYPES)),
            bigquery.ArrayQueryParameter(
                "write_stmt_types", "STRING", list(WRITE_STATEMENT_TYPES)
            ),
        ],
        use_legacy_sql=False,
    )
    rows = list(client.query(query, job_config=job_config).result())

    grouped: dict[str, list[bigquery.Row]] = defaultdict(list)
    for row in rows:
        key = f"{project}.{row['dataset_id']}.{row['table_id']}"
        grouped[key].append(row)
    return grouped


def _fmt_ts(ts: datetime | None) -> str:
    if ts is None:
        return "-"
    return ts.strftime("%Y-%m-%d %H:%M:%S %Z").strip()


def _fmt_bytes(n: int | None) -> str:
    if n is None:
        return "-"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(n)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:,.1f} {unit}"
        size /= 1024
    return f"{n} B"


def print_table_history(fqn: str, rows: list[bigquery.Row]) -> None:
    print(f"\n=== {fqn} ===")
    if not rows:
        print(f"  (no write jobs in the last {LOOKBACK_DAYS} days — "
              f"may be streaming, or run by SA without jobs.listAll perm)")
        return
    header = (
        f"{'#':>2}  {'creation_time':<28}  {'dur':>6}  "
        f"{'op':<28}  {'state':<8}  {'bytes':>12}  user"
    )
    print(header)
    print("-" * len(header))
    for i, r in enumerate(rows, 1):
        dur = f"{r['duration_sec']}s" if r["duration_sec"] is not None else "-"
        state = r["state"] or "-"
        if r["error_reason"]:
            state = f"{state}!"
        op = r["job_type"] or "-"
        if r["statement_type"]:
            op = f"{op}/{r['statement_type']}"
        print(
            f"{i:>2}  {_fmt_ts(r['creation_time']):<28}  {dur:>6}  "
            f"{op:<28}  {state:<8}  "
            f"{_fmt_bytes(r['total_bytes_processed']):>12}  {r['user_email'] or '-'}"
        )


def main() -> None:
    refs = [TableRef.parse(t) for t in TABLES]

    by_project: dict[str, list[TableRef]] = defaultdict(list)
    for ref in refs:
        by_project[ref.project].append(ref)

    all_results: dict[str, list[bigquery.Row]] = {}
    for project, refs_in_project in by_project.items():
        region = REGION_BY_PROJECT.get(project, DEFAULT_REGION)
        print(f"# querying {project} in {region} "
              f"({len(refs_in_project)} table(s), last {LOOKBACK_DAYS} days, top {LIMIT})")
        results = fetch_recent_loads(
            project=project,
            region=region,
            tables=refs_in_project,
            limit=LIMIT,
            lookback_days=LOOKBACK_DAYS,
        )
        all_results.update(results)

    for ref in refs:
        print_table_history(ref.fqn(), all_results.get(ref.fqn(), []))


if __name__ == "__main__":
    main()
