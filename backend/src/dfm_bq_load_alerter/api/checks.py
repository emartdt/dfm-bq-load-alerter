from __future__ import annotations

import logging
import zlib
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from dfm_bq_load_alerter.auth import require_admin
from dfm_bq_load_alerter.checks import run_checks
from dfm_bq_load_alerter.db.models import CheckSnapshot, CheckStatus
from dfm_bq_load_alerter.db.session import get_session

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/checks", tags=["checks"])

_RUN_NOW_LOCK_KEY = zlib.crc32(b"dfm-alert-run-now") & 0x7FFFFFFF


class SnapshotOut(BaseModel):
    table_id: int
    checked_at: datetime
    expected_check_time: datetime
    row_count: int | None
    last_modified: datetime | None
    status: CheckStatus
    failure_reasons: list[str]
    delta_percent_vs_yesterday: float | None


class RunNowResponse(BaseModel):
    triggered_at: datetime
    snapshot_count: int
    snapshots: list[SnapshotOut]


@router.post("/run-now", response_model=RunNowResponse)
async def run_now(
    session: Annotated[AsyncSession, Depends(get_session)],
    _principal: Annotated[dict, Depends(require_admin)],
    table_id: Annotated[int | None, Query(ge=1)] = None,
) -> RunNowResponse:
    """Trigger checks immediately. Single-flight via PG advisory lock (rev 2 P5)."""
    lock_acquired = (
        await session.execute(
            text("SELECT pg_try_advisory_lock(:k)"),
            {"k": _RUN_NOW_LOCK_KEY},
        )
    ).scalar_one()
    if not lock_acquired:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another run-now is already in progress.",
        )

    try:
        snapshots: list[CheckSnapshot] = await run_checks(
            session,
            table_ids=[table_id] if table_id is not None else None,
        )
        await session.commit()
    finally:
        await session.execute(
            text("SELECT pg_advisory_unlock(:k)"),
            {"k": _RUN_NOW_LOCK_KEY},
        )
        await session.commit()

    return RunNowResponse(
        triggered_at=datetime.now(),
        snapshot_count=len(snapshots),
        snapshots=[
            SnapshotOut(
                table_id=s.table_id,
                checked_at=s.checked_at,
                expected_check_time=s.expected_check_time,
                row_count=s.row_count,
                last_modified=s.last_modified,
                status=s.status,
                failure_reasons=s.failure_reasons,
                delta_percent_vs_yesterday=(
                    float(s.delta_percent_vs_yesterday)
                    if s.delta_percent_vs_yesterday is not None
                    else None
                ),
            )
            for s in snapshots
        ],
    )
