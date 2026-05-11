#!/usr/bin/env python
"""prune 후 누락된 18건의 모니터링 테이블을 batch_time=08:00, frequency=daily 로 등록.

`(project_id, dataset, table_name)` 가 이미 존재하면 skip.

사용 (backend/ 디렉터리 기준):
    DFM_ALERT_POSTGRES_DSN=... DFM_ALERT_BQ_PROJECT_ID=emart-datafabric \\
        uv run python scripts/seed_missing_tables.py           # preview
        uv run python scripts/seed_missing_tables.py --apply   # 실제 INSERT
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import time

from sqlalchemy import select

from dfm_bq_load_alerter.db.models import Frequency, Table
from dfm_bq_load_alerter.db.session import (
    dispose_engine,
    sessionmaker_factory,
)

SEED_LIST: tuple[str, ...] = (
    "emart-datafabric.bw.CODE_MATERIAL",
    "emart-datafabric.bw.PMATERIAL",
    "emart-datafabric.bw.PRT_OFFER",
    "emart-datafabric.bw.PVENDOR",
    "emart-datafabric.bw.PZCAMPNID",
    "emart-datafabric.bw.PZDATE",
    "emart-datafabric.bw.PZEVENTID",
    "emart-datafabric.bw.ZHR_AD007",
    "emart-datafabric.bw.ZMM_AD047",
    "emart-datafabric.bw.ZMM_AD130",
    "emart-datafabric.bw.ZMM_AD701",
    "emart-datafabric.bw.ZSD_AD500",
    "emart-datafabric.bw.ZSD_AD501",
    "emart-datafabric.bw.ZSD_AD704",
    "emart-datafabric.bw.ZSD_MG500",
    "smart-ruler-304409.cds_core.TB_BAIN_MEMBR_GRADE",
    "smart-ruler-304409.elt_verify.ELT_VERIFY_LOG",
    "smart-ruler-304419.cds_core.TB_AMT_CMMN_CUST_DNA_DATA",
)
BATCH_TIME = time(8, 0, 0)
FREQUENCY = Frequency.daily


def _split_fqn(fqn: str) -> tuple[str, str, str]:
    parts = fqn.split(".")
    if len(parts) != 3 or not all(parts):
        raise ValueError(f"invalid FQN: {fqn}")
    return parts[0], parts[1], parts[2]


async def _run(apply: bool) -> int:
    seeds = [_split_fqn(fqn) for fqn in SEED_LIST]
    sm = sessionmaker_factory()
    try:
        async with sm() as session:
            new_rows: list[Table] = []
            skipped: list[tuple[str, str, str]] = []
            for project_id, dataset, table_name in seeds:
                existing = await session.execute(
                    select(Table.id).where(
                        Table.project_id == project_id,
                        Table.dataset == dataset,
                        Table.table_name == table_name,
                    )
                )
                if existing.scalar_one_or_none() is not None:
                    skipped.append((project_id, dataset, table_name))
                    continue
                new_rows.append(
                    Table(
                        project_id=project_id,
                        dataset=dataset,
                        table_name=table_name,
                        frequency=FREQUENCY,
                        batch_time=BATCH_TIME,
                    )
                )

            print(f"[seed] target          : {len(seeds)}")
            print(f"[seed] to insert       : {len(new_rows)}")
            print(f"[seed] already present : {len(skipped)}")

            if new_rows:
                print("\n[seed] -- INSERT candidates --")
                for t in new_rows:
                    print(f"  + {t.project_id}.{t.dataset}.{t.table_name}")

            if skipped:
                print("\n[seed] -- already present (skipped) --")
                for proj, ds, tn in skipped:
                    print(f"  · {proj}.{ds}.{tn}")

            if not new_rows:
                print("\n[seed] nothing to insert.")
                return 0

            if not apply:
                print("\n[seed] dry-run only. Re-run with --apply to insert.")
                return 0

            session.add_all(new_rows)
            await session.commit()
            print(f"\n[seed] inserted {len(new_rows)} row(s).")
            return 0
    finally:
        await dispose_engine()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="실제 INSERT 수행. 미지정 시 dry-run.",
    )
    args = parser.parse_args()
    return asyncio.run(_run(apply=args.apply))


if __name__ == "__main__":
    raise SystemExit(main())
