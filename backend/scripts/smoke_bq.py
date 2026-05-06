#!/usr/bin/env python
"""BQ smoke test — exercise metadata, COUNT(*), and streaming-buffer paths.

Used as the PR-1 → PR-2 transition gate (rev 2 R1/R9/R12) and as a
helm `post-install` Job. Runs against a single table to verify:
  - GCP project/SA reachability (R1)
  - INFORMATION_SCHEMA/`__TABLES__` access (R12 — `bigquery.metadataViewer`)
  - COUNT(*) execution (R12 — `bigquery.jobUser`, `bigquery.dataViewer`)
  - STREAMING_TIMELINE visibility (R9 — streaming-insert buffer gap)

Exit codes: 0 = all paths OK, 1 = at least one path failed.

Usage:
    DFM_ALERT_BQ_PROJECT_ID=emart-datafabric \\
    GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json \\
    python -m dfm_bq_load_alerter.scripts.smoke_bq --dataset bw --table PZEVENTID
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from dfm_bq_load_alerter.bq.client import get_client
from dfm_bq_load_alerter.bq.metadata import fetch_metadata

KST = ZoneInfo("Asia/Seoul")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--table", required=True)
    parser.add_argument(
        "--force-count",
        action="store_true",
        help="Force COUNT(*) even when __TABLES__.row_count is present.",
    )
    args = parser.parse_args()

    client = get_client()
    print(f"[smoke] BQ project = {client.project}")
    print(f"[smoke] target     = {args.dataset}.{args.table}")
    print(f"[smoke] now (KST)  = {datetime.now(tz=KST).isoformat(timespec='seconds')}")

    try:
        meta = fetch_metadata(args.dataset, args.table, force_count=args.force_count)
    except Exception as exc:  # noqa: BLE001 — smoke must report all failures
        print(f"[smoke] FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(f"[smoke] last_modified         = {meta.last_modified}")
    print(f"[smoke] row_count             = {meta.row_count}")
    print(f"[smoke] used_count_fallback   = {meta.used_count_fallback}")
    print(f"[smoke] streaming_recent_rows = {meta.streaming_recent_rows}")
    print("[smoke] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
