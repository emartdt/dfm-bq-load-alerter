from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dfm_bq_load_alerter.bq.metadata import TableMetadata, fetch_metadata
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

    SKIP 스냅샷(마감 이전 미적재 판정 보류)은 row_count/last_modified 가
    실제 적재를 반영하지 않으므로 비교 베이스라인에서 제외한다.
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
        .where(CheckSnapshot.status != CheckStatus.skip)
        .order_by(CheckSnapshot.checked_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _fetch_metadatas_parallel(
    tables: list[Table],
    *,
    row_count_query_max_bytes: int,
) -> list[TableMetadata | BaseException]:
    """Call BigQuery `fetch_metadata` for each table concurrently.

    `fetch_metadata` is a blocking SDK call, so each request runs in a
    worker thread. The semaphore caps concurrent in-flight requests at
    `settings.bq_max_concurrency` to keep API quota usage predictable.

    Per-table BigQuery failures are captured (not re-raised) so a single
    table — e.g. one referencing a project without access permission —
    does not abort the whole cron cycle. The caller turns each captured
    exception into a FAIL snapshot with `bq_fetch_error: …` in
    `failure_reasons`.
    """
    if not tables:
        return []
    sem = asyncio.Semaphore(settings.bq_max_concurrency)
    targets = ", ".join(f"{t.dataset}.{t.table_name}" for t in tables)
    log.info(
        "bq fetch start: tables=%d concurrency=%d targets=[%s]",
        len(tables),
        settings.bq_max_concurrency,
        targets,
    )
    cycle_started = time.perf_counter()
    ok_count = 0
    fail_count = 0

    async def _one(table: Table) -> TableMetadata:
        nonlocal ok_count, fail_count
        label = f"{table.dataset}.{table.table_name}"
        max_retries = settings.bq_fetch_max_retries
        per_timeout = settings.bq_per_table_timeout_seconds
        last_exc: BaseException | None = None

        for attempt in range(1, max_retries + 1):
            started = time.perf_counter()
            try:
                async with sem:
                    async with asyncio.timeout(per_timeout):
                        meta = await asyncio.to_thread(
                            fetch_metadata,
                            table.dataset,
                            table.table_name,
                            project_id=table.project_id,
                            row_count_query=table.condition_query,
                            row_count_query_max_bytes=row_count_query_max_bytes,
                        )
            except TimeoutError:
                elapsed = time.perf_counter() - started
                last_exc = TimeoutError(
                    f"{label}: {per_timeout}s 초과 "
                    f"(시도 {attempt}/{max_retries})"
                )
                if attempt < max_retries:
                    backoff = min(2 ** attempt, 10)
                    log.warning(
                        "bq fetch timeout: %s took=%.2fs attempt=%d/%d — %ds 후 재시도",
                        label, elapsed, attempt, max_retries, backoff,
                    )
                    await asyncio.sleep(backoff)
                    continue
                fail_count += 1
                log.error(
                    "bq fetch timeout: %s took=%.2fs attempts=%d exhausted",
                    label, elapsed, max_retries,
                )
                raise last_exc
            except Exception:
                fail_count += 1
                elapsed = time.perf_counter() - started
                log.exception(
                    "bq fetch fail: %s took=%.2fs", label, elapsed
                )
                raise
            ok_count += 1
            elapsed = time.perf_counter() - started
            rows = meta.row_count if meta.row_count is not None else "?"
            log.info(
                "bq fetch ok: %s rows=%s took=%.2fs", label, rows, elapsed
            )
            return meta

        assert last_exc is not None
        raise last_exc

    try:
        return await asyncio.gather(
            *(_one(t) for t in tables), return_exceptions=True
        )
    finally:
        elapsed = time.perf_counter() - cycle_started
        log.info(
            "bq fetch done: ok=%d fail=%d total=%d elapsed=%.2fs",
            ok_count,
            fail_count,
            len(tables),
            elapsed,
        )


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
    row_count_query_max_bytes = (
        policy.condition_query_max_bytes
        if policy is not None
        else settings.condition_query_max_bytes
    )

    stmt = select(Table).where(Table.active.is_(True))
    if table_ids:
        stmt = stmt.where(Table.id.in_(table_ids))
    tables = (await session.execute(stmt)).scalars().all()

    eligible: list[Table] = []
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
        eligible.append(table)

    metadatas = await _fetch_metadatas_parallel(
        eligible, row_count_query_max_bytes=row_count_query_max_bytes
    )

    snapshots: list[CheckSnapshot] = []
    for table, metadata in zip(eligible, metadatas, strict=True):
        if isinstance(metadata, BaseException):
            if isinstance(metadata, TimeoutError):
                snapshot = CheckSnapshot(
                    table_id=table.id,
                    checked_at=actual,
                    expected_check_time=expected,
                    row_count=None,
                    last_modified=None,
                    status=CheckStatus.skip,
                    failure_reasons=[],
                    informational_notes=[
                        f"BQ 조회 시간 초과 (대기중): {metadata}"
                    ],
                    delta_percent_vs_yesterday=None,
                )
            else:
                snapshot = CheckSnapshot(
                    table_id=table.id,
                    checked_at=actual,
                    expected_check_time=expected,
                    row_count=None,
                    last_modified=None,
                    status=CheckStatus.fail,
                    failure_reasons=[
                        f"BigQuery 호출 실패: {type(metadata).__name__}: {metadata}"
                    ],
                    informational_notes=[],
                    delta_percent_vs_yesterday=None,
                )
            session.add(snapshot)
            snapshots.append(snapshot)
            continue

        if metadata.used_count_fallback:
            session.add(
                BqQueryLog(
                    table_id=table.id,
                    query_kind="count_fallback",
                    note=f"{table.dataset}.{table.table_name}",
                )
            )
        if table.condition_query is not None:
            session.add(
                BqQueryLog(
                    table_id=table.id,
                    query_kind="condition_query",
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
            informational_notes=result.informational_notes,
            delta_percent_vs_yesterday=result.delta_percent_vs_yesterday,
        )
        session.add(snapshot)
        snapshots.append(snapshot)

        if metadata.row_count is not None:
            table.latest_etl_row_count = metadata.row_count
        if metadata.last_modified is not None:
            table.latest_etl_datetime = metadata.last_modified

    await session.flush()
    return snapshots
