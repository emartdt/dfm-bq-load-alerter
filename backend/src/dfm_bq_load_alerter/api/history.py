"""점검 이력(check_snapshots) + 알림 이력(alert_events) 조회 API.

운영팀이 BO 에서 \"이 테이블이 언제 어떤 상태로 점검됐고 / 알람이 어디로
나갔는지\" 확인할 수 있도록 read-only 조회 엔드포인트를 노출.
페이지네이션은 단순 limit/offset (이력 양이 retention_days(기본 90일)
× 테이블 수 × 7회/일 정도로 제한됨).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from dfm_bq_load_alerter.auth import require_admin
from dfm_bq_load_alerter.db.models import (
    AlertEvent,
    Channel,
    CheckSnapshot,
    CheckStatus,
    EventStatus,
    Frequency,
    Table,
    TriggerKind,
)
from dfm_bq_load_alerter.db.session import get_session

router = APIRouter(prefix="/api/history", tags=["history"])


class SnapshotItem(BaseModel):
    id: int
    table_id: int
    project_id: str
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


_SNAPSHOT_SORT_COLUMNS = {
    "checked_at": CheckSnapshot.checked_at,
    "expected_check_time": CheckSnapshot.expected_check_time,
    "project_id": Table.project_id,
    "dataset": Table.dataset,
    "table_name": Table.table_name,
    "status": CheckSnapshot.status,
    "row_count": CheckSnapshot.row_count,
    "delta_percent_vs_yesterday": CheckSnapshot.delta_percent_vs_yesterday,
    "last_modified": CheckSnapshot.last_modified,
}


@router.get("/snapshots", response_model=SnapshotPage)
async def list_snapshots(
    session: Annotated[AsyncSession, Depends(get_session)],
    _principal: Annotated[dict, Depends(require_admin)],
    table_id: Annotated[int | None, Query(ge=1)] = None,
    status: Annotated[CheckStatus | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    sort_by: Annotated[str, Query()] = "checked_at",
    sort_dir: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SnapshotPage:
    base = select(CheckSnapshot).join(Table, Table.id == CheckSnapshot.table_id)
    count_stmt = (
        select(func.count(CheckSnapshot.id))
        .select_from(CheckSnapshot)
        .join(Table, Table.id == CheckSnapshot.table_id)
    )
    if table_id is not None:
        base = base.where(CheckSnapshot.table_id == table_id)
        count_stmt = count_stmt.where(CheckSnapshot.table_id == table_id)
    if status is not None:
        base = base.where(CheckSnapshot.status == status)
        count_stmt = count_stmt.where(CheckSnapshot.status == status)
    if q:
        like = f"%{q.strip()}%"
        search_clause = or_(
            Table.project_id.ilike(like),
            Table.dataset.ilike(like),
            Table.table_name.ilike(like),
        )
        base = base.where(search_clause)
        count_stmt = count_stmt.where(search_clause)

    sort_col = _SNAPSHOT_SORT_COLUMNS.get(sort_by, CheckSnapshot.checked_at)
    order = sort_col.desc() if sort_dir == "desc" else sort_col.asc()
    # 동일값 안정 정렬용 tiebreaker
    base = base.order_by(order, CheckSnapshot.id.desc()).limit(limit).offset(offset)

    rows = (
        await session.execute(
            base.add_columns(Table.project_id, Table.dataset, Table.table_name)
        )
    ).all()
    total = (await session.execute(count_stmt)).scalar_one()

    items: list[SnapshotItem] = []
    for snapshot, project_id, dataset, table_name in rows:
        items.append(
            SnapshotItem(
                id=snapshot.id,
                table_id=snapshot.table_id,
                project_id=project_id,
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


_EVENT_SORT_COLUMNS = {
    "sent_at": AlertEvent.sent_at,
    "trigger_kind": AlertEvent.trigger_kind,
    "channel": AlertEvent.channel,
    "status": AlertEvent.status,
    "payload_summary": AlertEvent.payload_summary,
    "error": AlertEvent.error,
}


@router.get("/events", response_model=EventPage)
async def list_events(
    session: Annotated[AsyncSession, Depends(get_session)],
    _principal: Annotated[dict, Depends(require_admin)],
    channel: Annotated[Channel | None, Query()] = None,
    event_status: Annotated[EventStatus | None, Query()] = None,
    trigger_kind: Annotated[TriggerKind | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    sort_by: Annotated[str, Query()] = "sent_at",
    sort_dir: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
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
    if q:
        like = f"%{q.strip()}%"
        search_clause = or_(
            AlertEvent.payload_summary.ilike(like),
            AlertEvent.error.ilike(like),
        )
        base = base.where(search_clause)
        count_stmt = count_stmt.where(search_clause)

    sort_col = _EVENT_SORT_COLUMNS.get(sort_by, AlertEvent.sent_at)
    order = sort_col.desc() if sort_dir == "desc" else sort_col.asc()
    base = base.order_by(order, AlertEvent.id.desc()).limit(limit).offset(offset)
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


class DailyStatPoint(BaseModel):
    bucket: date
    ok_count: int
    fail_count: int


class DailyStatsResponse(BaseModel):
    points: list[DailyStatPoint]


class MonthlyStatPoint(BaseModel):
    bucket: str  # "YYYY-MM"
    ok_count: int
    fail_count: int


class MonthlyStatsResponse(BaseModel):
    points: list[MonthlyStatPoint]


# 동일 (table, 슬롯) 에서 가장 최근 스냅샷 1건만 집계 — 같은 날(혹은 같은 달)에
# 여러 체크가 도는 경우 중복 카운트 방지.
_DAILY_STATS_SQL = text(
    """
    WITH latest_per_day AS (
        SELECT DISTINCT ON (cs.table_id, (cs.checked_at AT TIME ZONE 'Asia/Seoul')::date)
            cs.table_id,
            (cs.checked_at AT TIME ZONE 'Asia/Seoul')::date AS bucket,
            cs.status
        FROM check_snapshots cs
        JOIN tables t ON t.id = cs.table_id
        WHERE t.frequency = 'daily'
          AND cs.checked_at >= (now() AT TIME ZONE 'Asia/Seoul')::date - make_interval(days => :days)
        ORDER BY
            cs.table_id,
            (cs.checked_at AT TIME ZONE 'Asia/Seoul')::date,
            cs.checked_at DESC
    )
    SELECT
        bucket,
        SUM(CASE WHEN status = 'ok' THEN 1 ELSE 0 END) AS ok_count,
        SUM(CASE WHEN status = 'fail' THEN 1 ELSE 0 END) AS fail_count
    FROM latest_per_day
    GROUP BY bucket
    ORDER BY bucket
    """
)

_MONTHLY_STATS_SQL = text(
    """
    WITH latest_per_month AS (
        SELECT DISTINCT ON (
            cs.table_id,
            date_trunc('month', cs.checked_at AT TIME ZONE 'Asia/Seoul')
        )
            cs.table_id,
            date_trunc('month', cs.checked_at AT TIME ZONE 'Asia/Seoul')::date AS bucket,
            cs.status
        FROM check_snapshots cs
        JOIN tables t ON t.id = cs.table_id
        WHERE t.frequency = 'monthly'
          AND cs.checked_at >= date_trunc(
              'month',
              (now() AT TIME ZONE 'Asia/Seoul') - make_interval(months => :months - 1)
          )
        ORDER BY
            cs.table_id,
            date_trunc('month', cs.checked_at AT TIME ZONE 'Asia/Seoul'),
            cs.checked_at DESC
    )
    SELECT
        bucket,
        SUM(CASE WHEN status = 'ok' THEN 1 ELSE 0 END) AS ok_count,
        SUM(CASE WHEN status = 'fail' THEN 1 ELSE 0 END) AS fail_count
    FROM latest_per_month
    GROUP BY bucket
    ORDER BY bucket
    """
)


@router.get("/stats/daily", response_model=DailyStatsResponse)
async def daily_stats(
    session: Annotated[AsyncSession, Depends(get_session)],
    _principal: Annotated[dict, Depends(require_admin)],
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> DailyStatsResponse:
    """daily 적재 테이블의 KST 일자별 성공/실패 카운트.

    같은 (테이블, 일자) 에서 가장 최근 스냅샷 1건만 집계해 동일 슬롯의
    중복 체크가 카운트에 영향을 주지 않도록 한다.
    """
    rows = (await session.execute(_DAILY_STATS_SQL, {"days": days})).all()
    points = [
        DailyStatPoint(
            bucket=row.bucket,
            ok_count=int(row.ok_count or 0),
            fail_count=int(row.fail_count or 0),
        )
        for row in rows
    ]
    return DailyStatsResponse(points=points)


@router.get("/stats/monthly", response_model=MonthlyStatsResponse)
async def monthly_stats(
    session: Annotated[AsyncSession, Depends(get_session)],
    _principal: Annotated[dict, Depends(require_admin)],
    months: Annotated[int, Query(ge=1, le=36)] = 12,
) -> MonthlyStatsResponse:
    """monthly 적재 테이블의 KST 월별 성공/실패 카운트.

    같은 (테이블, 월) 에서 가장 최근 스냅샷 1건만 집계.
    """
    rows = (await session.execute(_MONTHLY_STATS_SQL, {"months": months})).all()
    points = [
        MonthlyStatPoint(
            bucket=row.bucket.strftime("%Y-%m"),
            ok_count=int(row.ok_count or 0),
            fail_count=int(row.fail_count or 0),
        )
        for row in rows
    ]
    return MonthlyStatsResponse(points=points)


class TableSuccessRateRow(BaseModel):
    table_id: int
    dataset: str
    table_name: str
    frequency: Frequency
    ok_count: int
    fail_count: int
    total: int
    success_rate: float  # 0.0 ~ 1.0


class TableSuccessRateResponse(BaseModel):
    days: int
    months: int
    rows: list[TableSuccessRateRow]


# 테이블별 성공률:
#   daily 테이블은 일자 단위로, monthly 테이블은 월 단위로 같은 슬롯의
#   최신 스냅샷 1건만 카운트한 뒤 (ok / (ok+fail)) 비율을 산출.
#   윈도우 내 ok/fail 스냅샷이 전혀 없는 테이블은 제외.
_TABLE_SUCCESS_RATE_SQL = text(
    """
    WITH daily_latest AS (
        SELECT DISTINCT ON (cs.table_id, (cs.checked_at AT TIME ZONE 'Asia/Seoul')::date)
            cs.table_id,
            cs.status
        FROM check_snapshots cs
        JOIN tables t ON t.id = cs.table_id
        WHERE t.frequency = 'daily'
          AND cs.checked_at >= (now() AT TIME ZONE 'Asia/Seoul')::date - make_interval(days => :days)
        ORDER BY
            cs.table_id,
            (cs.checked_at AT TIME ZONE 'Asia/Seoul')::date,
            cs.checked_at DESC
    ),
    monthly_latest AS (
        SELECT DISTINCT ON (
            cs.table_id,
            date_trunc('month', cs.checked_at AT TIME ZONE 'Asia/Seoul')
        )
            cs.table_id,
            cs.status
        FROM check_snapshots cs
        JOIN tables t ON t.id = cs.table_id
        WHERE t.frequency = 'monthly'
          AND cs.checked_at >= date_trunc(
              'month',
              (now() AT TIME ZONE 'Asia/Seoul') - make_interval(months => :months - 1)
          )
        ORDER BY
            cs.table_id,
            date_trunc('month', cs.checked_at AT TIME ZONE 'Asia/Seoul'),
            cs.checked_at DESC
    ),
    combined AS (
        SELECT * FROM daily_latest
        UNION ALL
        SELECT * FROM monthly_latest
    )
    SELECT
        t.id AS table_id,
        t.dataset,
        t.table_name,
        t.frequency,
        COALESCE(SUM(CASE WHEN c.status = 'ok' THEN 1 ELSE 0 END), 0)::int AS ok_count,
        COALESCE(SUM(CASE WHEN c.status = 'fail' THEN 1 ELSE 0 END), 0)::int AS fail_count
    FROM tables t
    LEFT JOIN combined c ON c.table_id = t.id
    GROUP BY t.id, t.dataset, t.table_name, t.frequency
    HAVING COALESCE(SUM(CASE WHEN c.status IN ('ok', 'fail') THEN 1 ELSE 0 END), 0) > 0
    ORDER BY t.dataset, t.table_name
    """
)


@router.get("/stats/table-success-rate", response_model=TableSuccessRateResponse)
async def table_success_rate(
    session: Annotated[AsyncSession, Depends(get_session)],
    _principal: Annotated[dict, Depends(require_admin)],
    days: Annotated[int, Query(ge=1, le=365)] = 30,
    months: Annotated[int, Query(ge=1, le=36)] = 12,
) -> TableSuccessRateResponse:
    """테이블별 성공률 (윈도우 내 ok / (ok+fail))."""
    rows = (
        await session.execute(
            _TABLE_SUCCESS_RATE_SQL, {"days": days, "months": months}
        )
    ).all()
    items: list[TableSuccessRateRow] = []
    for row in rows:
        ok = int(row.ok_count or 0)
        fail = int(row.fail_count or 0)
        total = ok + fail
        rate = ok / total if total > 0 else 0.0
        items.append(
            TableSuccessRateRow(
                table_id=row.table_id,
                dataset=row.dataset,
                table_name=row.table_name,
                frequency=Frequency(row.frequency),
                ok_count=ok,
                fail_count=fail,
                total=total,
                success_rate=round(rate, 4),
            )
        )
    return TableSuccessRateResponse(days=days, months=months, rows=items)
