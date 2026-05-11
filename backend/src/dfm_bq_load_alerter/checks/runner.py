from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dfm_bq_load_alerter.bq.metadata import fetch_metadata
from dfm_bq_load_alerter.checks.engine import (
    CheckResult,
    evaluate,
    is_skip_for_monthly,
    today_kst,
)
from dfm_bq_load_alerter.db.models import (
    AlertPolicy,
    BqQueryLog,
    CheckSnapshot,
    CheckStatus,
    Frequency,
    Table,
)
from dfm_bq_load_alerter.settings import settings

log = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")


def _previous_month_window(today: date) -> tuple[datetime, datetime]:
    """[start, end) covering the previous calendar month in KST."""
    first_of_this = today.replace(day=1)
    end = datetime.combine(first_of_this, datetime.min.time(), tzinfo=KST)
    if first_of_this.month == 1:
        first_of_prev = first_of_this.replace(year=first_of_this.year - 1, month=12)
    else:
        first_of_prev = first_of_this.replace(month=first_of_this.month - 1)
    start = datetime.combine(first_of_prev, datetime.min.time(), tzinfo=KST)
    return start, end


async def _baseline_snapshot(
    session: AsyncSession,
    *,
    table_id: int,
    frequency: Frequency,
    today: date,
) -> CheckSnapshot | None:
    """Most recent baseline snapshot for delta/inflow comparisons.

    - Daily tables → most recent yesterday(KST) snapshot.
    - Monthly tables → most recent snapshot from the previous calendar
      month in KST (typically the previous month's batch_day_of_month run).

    INSUFFICIENT_HISTORY rows are skipped so the baseline reflects an
    actual completed load.
    """
    if frequency == Frequency.monthly:
        start, end = _previous_month_window(today)
    else:
        yesterday = today - timedelta(days=1)
        start = datetime.combine(yesterday, datetime.min.time(), tzinfo=KST)
        end = datetime.combine(today, datetime.min.time(), tzinfo=KST)
    stmt = (
        select(CheckSnapshot)
        .where(CheckSnapshot.table_id == table_id)
        .where(CheckSnapshot.checked_at >= start)
        .where(CheckSnapshot.checked_at < end)
        .where(CheckSnapshot.status != CheckStatus.insufficient_history)
        .order_by(CheckSnapshot.checked_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def run_checks(
    session: AsyncSession,
    *,
    table_ids: list[int] | None = None,
    expected_check_time: datetime | None = None,
    actual_check_time: datetime | None = None,
) -> list[CheckSnapshot]:
    """Run checks against active tables and persist snapshots.

    - `table_ids=None` → all active tables
    - Monthly tables outside their batch day are skipped (rev 2 P10)
    - Each snapshot is committed in the caller's transaction
    """
    actual = actual_check_time or datetime.now(tz=KST)
    expected = expected_check_time or actual
    today = today_kst(actual)

    policy = await session.get(AlertPolicy, 1)
    default_buffer = (
        policy.default_buffer_minutes if policy is not None else 30
    )

    stmt = select(Table).where(Table.active.is_(True))
    if table_ids:
        stmt = stmt.where(Table.id.in_(table_ids))
    tables = (await session.execute(stmt)).scalars().all()

    snapshots: list[CheckSnapshot] = []
    for table in tables:
        if is_skip_for_monthly(table.frequency, table.batch_day_of_month, today):
            log.info(
                "skip monthly table %s.%s (today=%s, batch_dom=%s)",
                table.dataset,
                table.table_name,
                today,
                table.batch_day_of_month,
            )
            continue

        metadata = fetch_metadata(
            table.dataset, table.table_name, project_id=table.project_id
        )

        if metadata.used_count_fallback:
            session.add(
                BqQueryLog(
                    table_id=table.id,
                    query_kind="count_fallback",
                    note=f"{table.dataset}.{table.table_name}",
                )
            )

        threshold = float(
            table.delta_threshold_percent
            if table.delta_threshold_percent is not None
            else settings.default_threshold_percent
        )
        baseline = await _baseline_snapshot(
            session,
            table_id=table.id,
            frequency=table.frequency,
            today=today,
        )
        buffer_minutes = (
            table.buffer_minutes
            if table.buffer_minutes is not None
            else default_buffer
        )
        result: CheckResult = evaluate(
            metadata,
            yesterday_row_count=baseline.row_count if baseline else None,
            delta_threshold_percent=threshold,
            batch_time=table.batch_time,
            buffer_minutes=buffer_minutes,
            now=actual,
            cond_buffer_load=table.cond_buffer_load,
            cond_delta_rowcount=table.cond_delta_rowcount,
        )

        snapshot = CheckSnapshot(
            table_id=table.id,
            checked_at=actual,
            expected_check_time=expected,
            row_count=metadata.row_count,
            last_modified=metadata.last_modified,
            status=result.status,
            failure_reasons=result.failure_reasons,
            delta_percent_vs_yesterday=result.delta_percent_vs_yesterday,
        )
        session.add(snapshot)
        snapshots.append(snapshot)

    await session.flush()
    return snapshots
