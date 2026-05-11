from __future__ import annotations

import logging
import zlib
from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from dfm_bq_load_alerter.auth import require_admin
from dfm_bq_load_alerter.checks import run_checks
from dfm_bq_load_alerter.db.models import CheckSnapshot, CheckStatus
from dfm_bq_load_alerter.db.session import get_session
from dfm_bq_load_alerter.notifier.dispatcher import (
    build_dispatch_snapshots,
    dispatch,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/checks", tags=["checks"])
KST = ZoneInfo("Asia/Seoul")

_RUN_NOW_LOCK_KEY = zlib.crc32(b"dfm-alert-run-now") & 0x7FFFFFFF
_REPORT_NOW_LOCK_KEY = zlib.crc32(b"dfm-alert-report-now") & 0x7FFFFFFF


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
    notified: bool
    sent_events: int


@router.post("/run-now", response_model=RunNowResponse)
async def run_now(
    session: Annotated[AsyncSession, Depends(get_session)],
    _principal: Annotated[dict, Depends(require_admin)],
    table_id: Annotated[int | None, Query(ge=1)] = None,
    notify: Annotated[bool, Query()] = False,
) -> RunNowResponse:
    """Trigger checks immediately. Single-flight via PG advisory lock (rev 2 P5).

    `notify=true` additionally bundles the resulting snapshots into the
    configured channels (email + Teams) using the `check` trigger semantics —
    no send when there are zero FAIL rows. (rev 2 M3)
    """
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

    sent_events = 0
    try:
        snapshots: list[CheckSnapshot] = await run_checks(
            session,
            table_ids=[table_id] if table_id is not None else None,
        )
        if notify and snapshots:
            dispatch_rows = await build_dispatch_snapshots(session, snapshots)
            now = datetime.now(tz=KST)
            sent_events = await dispatch(
                session,
                snapshots=dispatch_rows,
                trigger_kind="check",
                expected=now,
                actual=now,
            )
        await session.commit()
    finally:
        await session.execute(
            text("SELECT pg_advisory_unlock(:k)"),
            {"k": _RUN_NOW_LOCK_KEY},
        )
        await session.commit()

    return RunNowResponse(
        triggered_at=datetime.now(tz=KST),
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
        notified=notify,
        sent_events=sent_events,
    )


@router.post("/report-now", response_model=RunNowResponse)
async def report_now(
    session: Annotated[AsyncSession, Depends(get_session)],
    _principal: Annotated[dict, Depends(require_admin)],
) -> RunNowResponse:
    """Trigger a 'report' dispatch immediately to verify SMTP / Teams wiring.

    Mirrors the 07:45 daily-report job's notification semantics: dispatch
    fires for every bucket regardless of FAIL count, skipping only when
    the snapshot list itself is empty. Intended for manual delivery tests.
    """
    lock_acquired = (
        await session.execute(
            text("SELECT pg_try_advisory_lock(:k)"),
            {"k": _REPORT_NOW_LOCK_KEY},
        )
    ).scalar_one()
    if not lock_acquired:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another report-now is already in progress.",
        )

    sent_events = 0
    try:
        now = datetime.now(tz=KST)
        snapshots: list[CheckSnapshot] = await run_checks(
            session,
            expected_check_time=now,
            actual_check_time=now,
        )
        dispatch_rows = await build_dispatch_snapshots(session, snapshots)
        sent_events = await dispatch(
            session,
            snapshots=dispatch_rows,
            trigger_kind="report",
            expected=now,
            actual=now,
        )
        await session.commit()
    finally:
        await session.execute(
            text("SELECT pg_advisory_unlock(:k)"),
            {"k": _REPORT_NOW_LOCK_KEY},
        )
        await session.commit()

    return RunNowResponse(
        triggered_at=datetime.now(tz=KST),
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
        notified=True,
        sent_events=sent_events,
    )
