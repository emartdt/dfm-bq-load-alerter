#!/usr/bin/env python
"""허용 목록(KEEP_LIST) 외의 tables 레코드를 일괄 정리.

기본은 dry-run. 실제 삭제는 `--apply` 지정 시 수행한다.

매칭 키: `(project_id_effective, dataset, table_name)`.
  - DB row 의 `project_id` 가 NULL 이면 `settings.bq_project_id` 로 폴백.

사용 (backend/ 디렉터리 기준):
    DFM_ALERT_POSTGRES_DSN=... DFM_ALERT_BQ_PROJECT_ID=emart-datafabric \\
        uv run python scripts/prune_tables.py           # preview (dry-run)
        uv run python scripts/prune_tables.py --apply   # 실제 삭제
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select

from dfm_bq_load_alerter.db.models import Table
from dfm_bq_load_alerter.db.session import (
    dispose_engine,
    sessionmaker_factory,
)
from dfm_bq_load_alerter.settings import settings

KEEP_LIST: tuple[str, ...] = (
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
    "smart-ruler-304409.cds_core.TB_DW_CUST_MASTR",
    "smart-ruler-304409.cds_core.TB_DW_DT_MASTR",
    "smart-ruler-304409.cds_core.TB_DW_OMNI_CUST_AGREE",
    "smart-ruler-304409.cds_core.TB_DW_POS_EVENT",
    "smart-ruler-304409.cds_core.TB_DW_POS_EVENT_PRDT_MASTR",
    "smart-ruler-304409.cds_core.TB_DW_POS_EVENT_PRT_STR_MASTR",
    "smart-ruler-304409.cds_core.TB_DW_POS_EVENT_RESULT",
    "smart-ruler-304409.cds_core.TB_DW_PRDT_CAT_CD",
    "smart-ruler-304409.cds_core.TB_DW_PRDT_DCODE_CD",
    "smart-ruler-304409.cds_core.TB_DW_PRDT_DI_CD",
    "smart-ruler-304409.cds_core.TB_DW_PRDT_GCODE_CD",
    "smart-ruler-304409.cds_core.TB_DW_PRDT_MASTR",
    "smart-ruler-304409.cds_core.TB_DW_PRDT_MCODE_CD",
    "smart-ruler-304409.cds_core.TB_DW_RCIPT_DETAIL",
    "smart-ruler-304409.cds_core.TB_DW_RCIPT_DETAIL_EMT_MALL",
    "smart-ruler-304409.cds_core.TB_DW_STR_MASTR",
    "smart-ruler-304409.cds_core.TB_DW_STR_PRDT",
    "smart-ruler-304409.elt_verify.ELT_VERIFY_LOG",
    "smart-ruler-304419.cds_core.TB_AMT_CMMN_CUST_DNA_DATA",
)


def _split_fqn(fqn: str) -> tuple[str, str, str]:
    parts = fqn.split(".")
    if len(parts) != 3 or not all(parts):
        raise ValueError(f"invalid FQN (expected project.dataset.table): {fqn}")
    return parts[0], parts[1], parts[2]


async def _run(apply: bool) -> int:
    default_project = settings.bq_project_id
    if not default_project:
        print(
            "[prune] WARN: DFM_ALERT_BQ_PROJECT_ID is empty — rows with project_id=NULL "
            "cannot be matched against the keep list and will be treated as DELETE candidates.",
            file=sys.stderr,
        )

    keep_set: set[tuple[str, str, str]] = {_split_fqn(fqn) for fqn in KEEP_LIST}

    sm = sessionmaker_factory()
    try:
        async with sm() as session:
            rows = (
                await session.execute(
                    select(Table).order_by(Table.dataset, Table.table_name)
                )
            ).scalars().all()

            to_delete: list[Table] = []
            to_keep: list[Table] = []
            for row in rows:
                effective_project = row.project_id or default_project
                key = (effective_project, row.dataset, row.table_name)
                (to_keep if key in keep_set else to_delete).append(row)

            present_keys = {
                (r.project_id or default_project, r.dataset, r.table_name) for r in rows
            }
            missing = sorted(keep_set - present_keys)

            print(f"[prune] DB rows total : {len(rows)}")
            print(f"[prune] keep matched  : {len(to_keep)} / {len(keep_set)} (keep list)")
            print(f"[prune] delete target : {len(to_delete)}")
            print(f"[prune] missing in DB : {len(missing)}  (in keep list but not present)")

            if to_delete:
                print("\n[prune] -- DELETE candidates --")
                for r in to_delete:
                    proj = r.project_id or f"(default={default_project})"
                    print(f"  - id={r.id:>5}  {proj}.{r.dataset}.{r.table_name}")

            if missing:
                print("\n[prune] -- MISSING in DB (no-op) --")
                for proj, ds, tn in missing:
                    print(f"  - {proj}.{ds}.{tn}")

            if not to_delete:
                print("\n[prune] nothing to delete.")
                return 0

            if not apply:
                print("\n[prune] dry-run only. Re-run with --apply to delete.")
                return 0

            for row in to_delete:
                await session.delete(row)
            await session.commit()
            print(f"\n[prune] deleted {len(to_delete)} row(s).")
            return 0
    finally:
        await dispose_engine()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="실제 삭제 수행. 미지정 시 dry-run.",
    )
    args = parser.parse_args()
    return asyncio.run(_run(apply=args.apply))


if __name__ == "__main__":
    raise SystemExit(main())
