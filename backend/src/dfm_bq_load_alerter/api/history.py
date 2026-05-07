"""점검 이력(check_snapshots) + 알림 이력(alert_events) 조회 API.

운영팀이 BO 에서 \"이 테이블이 언제 어떤 상태로 점검됐고 / 알람이 어디로
나갔는지\" 확인할 수 있도록 read-only 조회 엔드포인트를 노출.
페이지네이션은 단순 limit/offset (이력 양이 retention_days(기본 90일)
× 테이블 수 × 7회/일 정도로 제한됨).
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dfm_bq_load_alerter.auth import require_admin
from dfm_bq_load_alerter.db.models import (
    AlertEvent,
    Channel,
    CheckSnapshot,
    CheckStatus,
    EventStatus,
    Table,
    TriggerKind,
)
from dfm_bq_load_alerter.db.session import get_session

router = APIRouter(prefix="/api/history", tags=["history"])


class SnapshotItem(BaseModel):
    id: int
    table_id: int
    dataset: str
    table_name: str
    checked_at: datetime
    expected_check_time: datetime
    status: CheckStatus
    failure_reasons: list[str]
    row_count: int | None
    last_modified: datetime | None
    delta_percent_vs_yesterday: float | None


class SnapshotPage(BaseModel):
    items: list[SnapshotItem]
    total: int


class EventItem(BaseModel):
    id: int
    snapshot_id: int | None
    trigger_kind: TriggerKind
    channel: Channel
    status: EventStatus
    sent_at: datetime
    payload_summary: str | None
    error: str | None


class EventPage(BaseModel):
    items: list[EventItem]
    total: int


@router.get("/snapshots", response_model=SnapshotPage)
async def list_snapshots(
    session: Annotated[AsyncSession, Depends(get_session)],
    _principal: Annotated[dict, Depends(require_admin)],
    table_id: Annotated[int | None, Query(ge=1)] = None,
    status: Annotated[CheckStatus | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SnapshotPage:
    base = select(CheckSnapshot).join(Table, Table.id == CheckSnapshot.table_id)
    count_stmt = select(func.count(CheckSnapshot.id))
    if table_id is not None:
        base = base.where(CheckSnapshot.table_id == table_id)
        count_stmt = count_stmt.where(CheckSnapshot.table_id == table_id)
    if status is not None:
        base = base.where(CheckSnapshot.status == status)
        count_stmt = count_stmt.where(CheckSnapshot.status == status)

    base = base.order_by(CheckSnapshot.checked_at.desc()).limit(limit).offset(offset)

    rows = (await session.execute(base.add_columns(Table.dataset, Table.table_name))).all()
    total = (await session.execute(count_stmt)).scalar_one()

    items: list[SnapshotItem] = []
    for snapshot, dataset, table_name in rows:
        items.append(
            SnapshotItem(
                id=snapshot.id,
                table_id=snapshot.table_id,
                dataset=dataset,
                table_name=table_name,
                checked_at=snapshot.checked_at,
                expected_check_time=snapshot.expected_check_time,
                status=snapshot.status,
                failure_reasons=list(snapshot.failure_reasons or []),
                row_count=snapshot.row_count,
                last_modified=snapshot.last_modified,
                delta_percent_vs_yesterday=(
                    float(snapshot.delta_percent_vs_yesterday)
                    if snapshot.delta_percent_vs_yesterday is not None
                    else None
                ),
            )
        )
    return SnapshotPage(items=items, total=total)


@router.get("/events", response_model=EventPage)
async def list_events(
    session: Annotated[AsyncSession, Depends(get_session)],
    _principal: Annotated[dict, Depends(require_admin)],
    channel: Annotated[Channel | None, Query()] = None,
    event_status: Annotated[EventStatus | None, Query()] = None,
    trigger_kind: Annotated[TriggerKind | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EventPage:
    base = select(AlertEvent)
    count_stmt = select(func.count(AlertEvent.id))
    if channel is not None:
        base = base.where(AlertEvent.channel == channel)
        count_stmt = count_stmt.where(AlertEvent.channel == channel)
    if event_status is not None:
        base = base.where(AlertEvent.status == event_status)
        count_stmt = count_stmt.where(AlertEvent.status == event_status)
    if trigger_kind is not None:
        base = base.where(AlertEvent.trigger_kind == trigger_kind)
        count_stmt = count_stmt.where(AlertEvent.trigger_kind == trigger_kind)

    base = base.order_by(AlertEvent.sent_at.desc()).limit(limit).offset(offset)
    rows = (await session.execute(base)).scalars().all()
    total = (await session.execute(count_stmt)).scalar_one()

    return EventPage(
        items=[
            EventItem(
                id=row.id,
                snapshot_id=row.snapshot_id,
                trigger_kind=row.trigger_kind,
                channel=row.channel,
                status=row.status,
                sent_at=row.sent_at,
                payload_summary=row.payload_summary,
                error=row.error,
            )
            for row in rows
        ],
        total=total,
    )
