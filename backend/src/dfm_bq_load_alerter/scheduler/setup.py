"""APScheduler factory + cron job registration (rev 2 P4).

Uses `MemoryJobStore` (not the SQLAlchemy job store) because the seven
KST cron triggers are static across deploys — re-registered on every
Pod startup. PG-backed job persistence is unnecessary for a fixed
trigger set and simplifies the operations surface (no schema drift
concerns with `dfm_apscheduler_jobs`).

`misfire_grace_time` is differentiated per job (rev 2 P4):
- check jobs: 120s (skip catch-up beyond two minutes; let the next cron
  handle it to avoid duplicate alerts).
- 07:45 report: 600s (always send the daily report once, even if late).
"""
from __future__ import annotations

import logging
from datetime import time

from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

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


def register_jobs(scheduler: AsyncIOScheduler) -> None:
    """Register the seven cron triggers (six checks + one report)."""
    for moment in CHECK_TIMES:
        job_id = f"check-{moment.hour:02d}{moment.minute:02d}"
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

    scheduler.add_job(
        report_745,
        trigger=CronTrigger(
            hour=REPORT_TIME.hour,
            minute=REPORT_TIME.minute,
            timezone=settings.scheduler_timezone,
        ),
        args=[REPORT_TIME],
        id="report-0745",
        replace_existing=True,
        misfire_grace_time=settings.misfire_grace_report_seconds,
        coalesce=True,
    )
    log.info("registered job report-0745 @ 07:45 KST")
