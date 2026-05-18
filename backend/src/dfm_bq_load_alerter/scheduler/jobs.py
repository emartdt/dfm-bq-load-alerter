"""Cron job functions invoked by APScheduler.

Each job opens its own async session, runs the checks, persists snapshots,
and dispatches notifications — emitting a single email + Teams message per
trigger (rev 2 M3 bundling).
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete

from dfm_bq_load_alerter.checks import run_checks
from dfm_bq_load_alerter.db.models import AlertEvent, AlertPolicy, CheckSnapshot
from dfm_bq_load_alerter.db.session import sessionmaker_factory
from dfm_bq_load_alerter.notifier.dispatcher import build_dispatch_snapshots, dispatch
from dfm_bq_load_alerter.settings import settings

log = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")


def _expected_check_datetime(moment: time, *, now: datetime | None = None) -> datetime:
    """Compose the expected KST datetime for today's cron firing."""
    base = (now or datetime.now(tz=KST)).astimezone(KST)
    return base.replace(
        hour=moment.hour, minute=moment.minute, second=0, microsecond=0
    )


async def check_at(job_id: str, moment: time) -> None:
    """Run all active table checks for a single cron trigger.

    Notification semantics: trigger='check' — bundled email+Teams send when
    one or more snapshots are FAIL; otherwise no message.
    """
    actual = datetime.now(tz=KST)
    expected = _expected_check_datetime(moment, now=actual)
    log.info(
        "[%s] cron fired (expected=%s actual=%s)",
        job_id,
        expected.isoformat(timespec="seconds"),
        actual.isoformat(timespec="seconds"),
    )

    sm = sessionmaker_factory()
    async with sm() as session:
        snapshots = await run_checks(
            session, expected_check_time=expected, actual_check_time=actual
        )
        dispatch_rows = await build_dispatch_snapshots(session, snapshots)
        sent = await dispatch(
            session,
            snapshots=dispatch_rows,
            trigger_kind="check",
            expected=expected,
            actual=actual,
        )
        await session.commit()
    log.info("[%s] cron complete: snapshots=%d events=%d", job_id, len(snapshots), sent)


async def report_745(moment: time = time(7, 45)) -> None:
    """Daily summary report at 07:45 KST.

    Notification semantics: trigger='report' — always sends once even if
    every table is OK. Includes OK / INSUFFICIENT_HISTORY sections.
    """
    actual = datetime.now(tz=KST)
    expected = _expected_check_datetime(moment, now=actual)
    log.info(
        "[report-0745] cron fired (expected=%s actual=%s)",
        expected.isoformat(timespec="seconds"),
        actual.isoformat(timespec="seconds"),
    )

    sm = sessionmaker_factory()
    async with sm() as session:
        snapshots = await run_checks(
            session, expected_check_time=expected, actual_check_time=actual
        )
        dispatch_rows = await build_dispatch_snapshots(session, snapshots)
        sent = await dispatch(
            session,
            snapshots=dispatch_rows,
            trigger_kind="report",
            expected=expected,
            actual=actual,
        )
        await session.commit()
    log.info(
        "[report-0745] cron complete: snapshots=%d events=%d (settings.scheduler_enabled=%s)",
        len(snapshots),
        sent,
        settings.scheduler_enabled,
    )


async def cleanup_history(now: datetime | None = None) -> dict[str, int | str]:
    """Delete check_snapshots/alert_events older than policy.retention_days.

    Reads ``alert_policy.retention_days`` each run so policy changes take
    effect on the next cleanup tick without a redeploy. Falls back to
    ``settings.retention_days`` when the policy row is absent.
    """
    actual = (now or datetime.now(tz=KST)).astimezone(KST)
    log.info(
        "[cleanup-history] cron fired (actual=%s)",
        actual.isoformat(timespec="seconds"),
    )

    sm = sessionmaker_factory()
    async with sm() as session:
        policy = await session.get(AlertPolicy, 1)
        retention_days = policy.retention_days if policy else settings.retention_days
        cutoff = actual.astimezone(UTC) - timedelta(days=retention_days)
        snap_result = await session.execute(
            delete(CheckSnapshot).where(CheckSnapshot.checked_at < cutoff)
        )
        event_result = await session.execute(
            delete(AlertEvent).where(AlertEvent.sent_at < cutoff)
        )
        await session.commit()
    deleted_snapshots = snap_result.rowcount or 0
    deleted_events = event_result.rowcount or 0
    log.info(
        "[cleanup-history] cron complete: retention=%dd cutoff=%s "
        "deleted snapshots=%d events=%d",
        retention_days,
        cutoff.isoformat(timespec="seconds"),
        deleted_snapshots,
        deleted_events,
    )
    return {
        "retention_days": retention_days,
        "cutoff": cutoff.isoformat(timespec="seconds"),
        "deleted_snapshots": deleted_snapshots,
        "deleted_events": deleted_events,
    }
