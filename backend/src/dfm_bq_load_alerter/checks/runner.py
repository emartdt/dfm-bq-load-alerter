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
    BqQueryLog,
    CheckSnapshot,
    CheckStatus,
    Table,
)
from dfm_bq_load_alerter.settings import settings

log = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")


async def _yesterday_row_count(
    session: AsyncSession, *, table_id: int, today: date
) -> int | None:
    """Return the most recent snapshot's row_count from yesterday's calendar day."""
    yesterday = today - timedelta(days=1)
    start = datetime.combine(yesterday, datetime.min.time(), tzinfo=KST)
    end = datetime.combine(today, datetime.min.time(), tzinfo=KST)
    stmt = (
        select(CheckSnapshot.row_count)
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

        metadata = fetch_metadata(table.dataset, table.table_name)

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
        yesterday_count = await _yesterday_row_count(
            session, table_id=table.id, today=today
        )
        result: CheckResult = evaluate(
            metadata,
            yesterday_row_count=yesterday_count,
            delta_threshold_percent=threshold,
            deadline_time=table.deadline_time,
            now=actual,
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
