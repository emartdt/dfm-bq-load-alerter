"""Verify scheduler factory and cron job registration (rev 2 P4)."""
from __future__ import annotations

from datetime import time

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from dfm_bq_load_alerter.scheduler import (
    CHECK_TIMES,
    REPORT_TIME,
    build_scheduler,
    register_jobs,
)
from dfm_bq_load_alerter.settings import settings


def test_check_times_match_spec() -> None:
    assert (
        time(6, 0),
        time(7, 0),
        time(8, 0),
        time(8, 20),
        time(8, 40),
        time(9, 0),
    ) == CHECK_TIMES
    assert time(7, 45) == REPORT_TIME


def test_build_scheduler_uses_kst_timezone() -> None:
    scheduler = build_scheduler()
    assert isinstance(scheduler, AsyncIOScheduler)
    assert str(scheduler.timezone) == settings.scheduler_timezone


def test_register_jobs_creates_seven_cron_triggers() -> None:
    scheduler = build_scheduler()
    register_jobs(scheduler)
    jobs = scheduler.get_jobs()
    assert len(jobs) == 7
    ids = {j.id for j in jobs}
    assert ids == {
        "check-0600",
        "check-0700",
        "check-0800",
        "check-0820",
        "check-0840",
        "check-0900",
        "report-0745",
    }
    for job in jobs:
        assert isinstance(job.trigger, CronTrigger)


def test_check_jobs_use_check_misfire_grace() -> None:
    scheduler = build_scheduler()
    register_jobs(scheduler)
    check_jobs = [j for j in scheduler.get_jobs() if j.id.startswith("check-")]
    assert all(
        j.misfire_grace_time == settings.misfire_grace_check_seconds for j in check_jobs
    )


def test_report_job_uses_report_misfire_grace() -> None:
    scheduler = build_scheduler()
    register_jobs(scheduler)
    report = next(j for j in scheduler.get_jobs() if j.id == "report-0745")
    assert report.misfire_grace_time == settings.misfire_grace_report_seconds


def test_register_jobs_creates_seven_jobs_on_fresh_scheduler() -> None:
    """Each new scheduler instance gets exactly 7 jobs (startup invariant)."""
    scheduler1 = build_scheduler()
    register_jobs(scheduler1)
    scheduler2 = build_scheduler()
    register_jobs(scheduler2)
    assert len(scheduler1.get_jobs()) == 7
    assert len(scheduler2.get_jobs()) == 7


@pytest.mark.parametrize(
    "minute,expected_id",
    [(0, "check-0600"), (20, "check-0820"), (40, "check-0840")],
)
def test_check_job_id_format(minute: int, expected_id: str) -> None:
    scheduler = build_scheduler()
    register_jobs(scheduler)
    if minute == 0:
        assert any(j.id == "check-0600" for j in scheduler.get_jobs())
    assert any(j.id == expected_id for j in scheduler.get_jobs())
