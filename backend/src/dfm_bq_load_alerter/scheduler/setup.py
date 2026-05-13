"""APScheduler factory + cron job registration (rev 2 P4).

`register_dynamic_jobs(scheduler)` is the production entrypoint: it pulls
`alert_policy.check_times` / `report_time` from the DB and installs a
polling job that re-applies the schedule when the policy row changes —
no Pod restart required.

`register_jobs(scheduler)` is the legacy/sync entrypoint that registers
the hardcoded fallback constants. It is kept for tests and as a safety
net for environments where the DB row has not been provisioned yet.

`MemoryJobStore` (not the SQLAlchemy job store) is used because the cron
trigger set is re-derived from the policy row on each reload; PG-backed
job persistence would conflict with that model.

`misfire_grace_time` is differentiated per job:
- check jobs: 120s (skip catch-up beyond two minutes; let the next cron
  handle it to avoid duplicate alerts).
- report jobs: 600s (always send the daily report once, even if late).
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime, time

from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from dfm_bq_load_alerter.db.models import AlertPolicy
from dfm_bq_load_alerter.db.session import sessionmaker_factory
from dfm_bq_load_alerter.scheduler.jobs import check_at, report_745
from dfm_bq_load_alerter.settings import settings

log = logging.getLogger(__name__)

CHECK_TIMES: tuple[time, ...] = (
    time(6, 0),
    time(7, 0),
    time(8, 0),
    time(8, 20),
    time(8, 40),
    time(9, 0),
)
REPORT_TIME: time = time(7, 45)

CHECK_JOB_PREFIX = "check-"
REPORT_JOB_PREFIX = "report-"
POLICY_RELOAD_JOB_ID = "_policy-reload"
POLICY_POLL_SECONDS = 30


def build_scheduler() -> AsyncIOScheduler:
    """Build a configured AsyncIOScheduler. Caller must `start()` it."""
    return AsyncIOScheduler(
        jobstores={"default": MemoryJobStore()},
        timezone=settings.scheduler_timezone,
        job_defaults={
            "coalesce": True,
            "max_instances": 1,
        },
    )


def _check_job_id(moment: time) -> str:
    return f"{CHECK_JOB_PREFIX}{moment.hour:02d}{moment.minute:02d}"


def _report_job_id(moment: time) -> str:
    return f"{REPORT_JOB_PREFIX}{moment.hour:02d}{moment.minute:02d}"


def _add_check_job(scheduler: AsyncIOScheduler, moment: time) -> str:
    job_id = _check_job_id(moment)
    scheduler.add_job(
        check_at,
        trigger=CronTrigger(
            hour=moment.hour,
            minute=moment.minute,
            timezone=settings.scheduler_timezone,
        ),
        args=[job_id, moment],
        id=job_id,
        replace_existing=True,
        misfire_grace_time=settings.misfire_grace_check_seconds,
        coalesce=True,
    )
    log.info("registered job %s @ %02d:%02d KST", job_id, moment.hour, moment.minute)
    return job_id


def _add_report_job(scheduler: AsyncIOScheduler, moment: time) -> str:
    job_id = _report_job_id(moment)
    scheduler.add_job(
        report_745,
        trigger=CronTrigger(
            hour=moment.hour,
            minute=moment.minute,
            timezone=settings.scheduler_timezone,
        ),
        args=[moment],
        id=job_id,
        replace_existing=True,
        misfire_grace_time=settings.misfire_grace_report_seconds,
        coalesce=True,
    )
    log.info("registered job %s @ %02d:%02d KST", job_id, moment.hour, moment.minute)
    return job_id


def register_jobs(scheduler: AsyncIOScheduler) -> None:
    """Register cron jobs from the static fallback constants (sync)."""
    for moment in CHECK_TIMES:
        _add_check_job(scheduler, moment)
    _add_report_job(scheduler, REPORT_TIME)


def _sync_check_jobs(
    scheduler: AsyncIOScheduler, check_times: Iterable[time]
) -> None:
    desired: set[str] = set()
    for moment in check_times:
        desired.add(_add_check_job(scheduler, moment))
    for job in list(scheduler.get_jobs()):
        if job.id.startswith(CHECK_JOB_PREFIX) and job.id not in desired:
            scheduler.remove_job(job.id)
            log.info("removed stale job %s", job.id)


def _sync_report_job(scheduler: AsyncIOScheduler, report_time: time) -> None:
    desired_id = _add_report_job(scheduler, report_time)
    for job in list(scheduler.get_jobs()):
        if job.id.startswith(REPORT_JOB_PREFIX) and job.id != desired_id:
            scheduler.remove_job(job.id)
            log.info("removed stale job %s", job.id)


async def _fetch_policy_schedule() -> tuple[tuple[time, ...], time, datetime | None]:
    sm = sessionmaker_factory()
    async with sm() as session:
        policy = await session.get(AlertPolicy, 1)
        if policy is None:
            log.info("scheduler: alert_policy row missing, using fallback constants")
            return CHECK_TIMES, REPORT_TIME, None
        parsed: list[time] = []
        for raw in policy.check_times or []:
            try:
                parsed.append(time.fromisoformat(raw))
            except ValueError:
                log.warning("scheduler: skipping invalid check_times entry %r", raw)
        if not parsed:
            parsed = list(CHECK_TIMES)
        return tuple(parsed), policy.report_time, policy.updated_at


_last_policy_updated_at: datetime | None = None


def _reset_policy_cache() -> None:
    """Forget the last-applied policy timestamp (called on leader loss)."""
    global _last_policy_updated_at
    _last_policy_updated_at = None


async def reload_jobs_from_policy(
    scheduler: AsyncIOScheduler, *, force: bool = False
) -> None:
    """Re-apply check/report cron triggers from the DB policy row.

    When `force=False`, the call is a no-op if `policy.updated_at` has not
    changed since the last reload. The polling job uses `force=False`;
    initial registration uses `force=True` to always seed jobs even when
    the DB cache flag still matches.
    """
    global _last_policy_updated_at
    check_times, report_time, updated_at = await _fetch_policy_schedule()
    checks_str = ", ".join(t.strftime("%H:%M") for t in check_times)
    report_str = report_time.strftime("%H:%M")
    if (
        not force
        and updated_at is not None
        and updated_at == _last_policy_updated_at
    ):
        log.info(
            "scheduler: policy poll — unchanged (updated_at=%s, checks=[%s], report=%s)",
            updated_at,
            checks_str,
            report_str,
        )
        return
    _sync_check_jobs(scheduler, check_times)
    _sync_report_job(scheduler, report_time)
    previous = _last_policy_updated_at
    _last_policy_updated_at = updated_at
    log.info(
        "scheduler: policy applied (updated_at=%s, prev=%s, checks=[%s], report=%s)",
        updated_at,
        previous,
        checks_str,
        report_str,
    )


async def _poll_reload(scheduler: AsyncIOScheduler) -> None:
    try:
        await reload_jobs_from_policy(scheduler)
    except Exception:  # noqa: BLE001
        log.exception("scheduler: policy reload failed")


async def register_dynamic_jobs(scheduler: AsyncIOScheduler) -> None:
    """DB-driven registration + polling for policy changes (production)."""
    _reset_policy_cache()
    await reload_jobs_from_policy(scheduler, force=True)
    scheduler.add_job(
        _poll_reload,
        trigger=IntervalTrigger(seconds=POLICY_POLL_SECONDS),
        args=[scheduler],
        id=POLICY_RELOAD_JOB_ID,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    log.info(
        "scheduler: policy poll job registered (every %ds)", POLICY_POLL_SECONDS
    )
