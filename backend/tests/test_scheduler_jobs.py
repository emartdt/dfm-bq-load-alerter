"""Tests for the scheduler job functions (check_at, report_745).

These verify that the job composes the expected/actual datetime correctly
and dispatches with the right trigger_kind. The DB session and dispatcher
are mocked so no PG/SMTP/Teams is needed.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, time
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time

from dfm_bq_load_alerter.db.models import (
    AlertEvent,
    Channel,
    EventStatus,
    TriggerKind,
)
from dfm_bq_load_alerter.scheduler.jobs import (
    _expected_check_datetime,
    check_at,
    cleanup_history,
    report_745,
)

KST = ZoneInfo("Asia/Seoul")


def test_expected_check_datetime_clamps_to_kst_today() -> None:
    with freeze_time(datetime(2026, 5, 6, 14, 30, tzinfo=ZoneInfo("UTC"))):
        # UTC 14:30 on 2026-05-06 == KST 23:30 on 2026-05-06
        result = _expected_check_datetime(time(8, 0))
        assert result.tzinfo == KST
        assert result.year == 2026
        assert result.month == 5
        assert result.day == 6
        assert result.hour == 8
        assert result.minute == 0
        assert result.second == 0


@pytest.mark.asyncio
async def test_check_at_dispatches_with_check_trigger(monkeypatch) -> None:
    fake_session = AsyncMock()
    fake_session.commit = AsyncMock()
    fake_session.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session.__aexit__ = AsyncMock(return_value=None)

    fake_sm = MagicMock(return_value=fake_session)
    monkeypatch.setattr(
        "dfm_bq_load_alerter.scheduler.jobs.sessionmaker_factory",
        MagicMock(return_value=fake_sm),
    )

    run_checks_mock = AsyncMock(return_value=[])
    build_dispatch_snapshots_mock = AsyncMock(return_value=[])
    dispatch_mock = AsyncMock(return_value=0)

    monkeypatch.setattr(
        "dfm_bq_load_alerter.scheduler.jobs.run_checks", run_checks_mock
    )
    monkeypatch.setattr(
        "dfm_bq_load_alerter.scheduler.jobs.build_dispatch_snapshots",
        build_dispatch_snapshots_mock,
    )
    monkeypatch.setattr(
        "dfm_bq_load_alerter.scheduler.jobs.dispatch", dispatch_mock
    )

    await check_at("check-0800", time(8, 0))

    run_checks_mock.assert_awaited_once()
    dispatch_mock.assert_awaited_once()
    assert dispatch_mock.await_args.kwargs["trigger_kind"] == "check"


@pytest.mark.asyncio
async def test_report_745_dispatches_with_report_trigger(monkeypatch) -> None:
    fake_session = AsyncMock()
    fake_session.commit = AsyncMock()
    fake_session.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session.__aexit__ = AsyncMock(return_value=None)
    fake_sm = MagicMock(return_value=fake_session)
    monkeypatch.setattr(
        "dfm_bq_load_alerter.scheduler.jobs.sessionmaker_factory",
        MagicMock(return_value=fake_sm),
    )

    monkeypatch.setattr(
        "dfm_bq_load_alerter.scheduler.jobs.run_checks", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        "dfm_bq_load_alerter.scheduler.jobs.build_dispatch_snapshots",
        AsyncMock(return_value=[]),
    )
    dispatch_mock = AsyncMock(return_value=0)
    monkeypatch.setattr(
        "dfm_bq_load_alerter.scheduler.jobs.dispatch", dispatch_mock
    )

    await report_745()
    assert dispatch_mock.await_args.kwargs["trigger_kind"] == "report"


def _make_cleanup_session(*, policy_retention_days: int | None, deleted: tuple[int, int]):
    """Build an AsyncMock session preloaded with policy + execute rowcounts."""
    fake_session = AsyncMock()
    fake_session.commit = AsyncMock()
    fake_session.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session.__aexit__ = AsyncMock(return_value=None)
    if policy_retention_days is None:
        fake_session.get = AsyncMock(return_value=None)
    else:
        policy = MagicMock()
        policy.retention_days = policy_retention_days
        fake_session.get = AsyncMock(return_value=policy)
    snap_result = MagicMock(rowcount=deleted[0])
    event_result = MagicMock(rowcount=deleted[1])
    fake_session.execute = AsyncMock(side_effect=[snap_result, event_result])
    return fake_session


@pytest.mark.asyncio
async def test_cleanup_history_uses_policy_retention(monkeypatch) -> None:
    fake_session = _make_cleanup_session(policy_retention_days=30, deleted=(5, 3))
    monkeypatch.setattr(
        "dfm_bq_load_alerter.scheduler.jobs.sessionmaker_factory",
        MagicMock(return_value=MagicMock(return_value=fake_session)),
    )

    now = datetime(2026, 5, 15, 3, 0, tzinfo=KST)
    result = await cleanup_history(now=now)

    assert result["retention_days"] == 30
    assert result["deleted_snapshots"] == 5
    assert result["deleted_events"] == 3
    assert fake_session.execute.await_count == 2
    fake_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_cleanup_history_falls_back_to_settings_when_policy_missing(
    monkeypatch,
) -> None:
    fake_session = _make_cleanup_session(policy_retention_days=None, deleted=(0, 0))
    monkeypatch.setattr(
        "dfm_bq_load_alerter.scheduler.jobs.sessionmaker_factory",
        MagicMock(return_value=MagicMock(return_value=fake_session)),
    )
    monkeypatch.setattr(
        "dfm_bq_load_alerter.scheduler.jobs.settings.retention_days", 90
    )

    result = await cleanup_history(now=datetime(2026, 5, 15, 3, 0, tzinfo=KST))
    assert result["retention_days"] == 90


def _make_timeout_session():
    """deadline 초과 기록용 세션 mock — add는 동기 메서드이므로 MagicMock."""
    fake_session = AsyncMock()
    fake_session.add = MagicMock()
    fake_session.commit = AsyncMock()
    fake_session.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session.__aexit__ = AsyncMock(return_value=None)
    return fake_session


@pytest.mark.asyncio
async def test_check_at_deadline_초과시_failed_이벤트_기록(monkeypatch) -> None:
    """job이 job_timeout_seconds를 넘기면 예외 없이 종료하고 alert_events에 남긴다."""
    fake_session = _make_timeout_session()
    monkeypatch.setattr(
        "dfm_bq_load_alerter.scheduler.jobs.sessionmaker_factory",
        MagicMock(return_value=MagicMock(return_value=fake_session)),
    )
    monkeypatch.setattr(
        "dfm_bq_load_alerter.scheduler.jobs.settings.job_timeout_seconds",
        0.05,
        raising=False,
    )

    async def slow_run_checks(*args, **kwargs):
        await asyncio.sleep(30)

    monkeypatch.setattr(
        "dfm_bq_load_alerter.scheduler.jobs.run_checks", slow_run_checks
    )

    # TimeoutError가 밖으로 새면 안 된다 (APScheduler 슬롯 보호가 목적)
    await check_at("check-0800", time(8, 0))

    fake_session.add.assert_called_once()
    event = fake_session.add.call_args.args[0]
    assert isinstance(event, AlertEvent)
    assert event.trigger_kind == TriggerKind.check
    assert event.channel == Channel.email
    assert event.status == EventStatus.failed
    assert event.payload_summary == "job timeout · check-0800"
    assert "deadline exceeded" in event.error
    fake_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_report_745_deadline_초과시_report_트리거로_기록(monkeypatch) -> None:
    fake_session = _make_timeout_session()
    monkeypatch.setattr(
        "dfm_bq_load_alerter.scheduler.jobs.sessionmaker_factory",
        MagicMock(return_value=MagicMock(return_value=fake_session)),
    )
    monkeypatch.setattr(
        "dfm_bq_load_alerter.scheduler.jobs.settings.job_timeout_seconds",
        0.05,
        raising=False,
    )

    async def slow_run_checks(*args, **kwargs):
        await asyncio.sleep(30)

    monkeypatch.setattr(
        "dfm_bq_load_alerter.scheduler.jobs.run_checks", slow_run_checks
    )

    await report_745()

    event = fake_session.add.call_args.args[0]
    assert event.trigger_kind == TriggerKind.report
    assert event.payload_summary == "job timeout · report-0745"


@pytest.mark.asyncio
async def test_cleanup_history_deadline_초과시_DB기록_없이_None_반환(monkeypatch) -> None:
    """cleanup은 알람과 무관하므로 timeout 시 로그만 남긴다 (spec 결정)."""
    fake_session = _make_timeout_session()

    async def slow_get(*args, **kwargs):
        await asyncio.sleep(30)

    fake_session.get = slow_get
    monkeypatch.setattr(
        "dfm_bq_load_alerter.scheduler.jobs.sessionmaker_factory",
        MagicMock(return_value=MagicMock(return_value=fake_session)),
    )
    monkeypatch.setattr(
        "dfm_bq_load_alerter.scheduler.jobs.settings.job_timeout_seconds",
        0.05,
        raising=False,
    )

    result = await cleanup_history(now=datetime(2026, 5, 15, 3, 0, tzinfo=KST))

    assert result is None
    fake_session.add.assert_not_called()


@pytest.mark.asyncio
async def test_deadline_이벤트_기록_실패해도_예외를_삼킨다(monkeypatch, caplog) -> None:
    """timeout 기록용 세션 생성 자체가 실패해도 job은 조용히 끝나야 한다."""
    call_count = 0
    fake_session = _make_timeout_session()

    def failing_factory():
        nonlocal call_count
        call_count += 1
        if call_count >= 2:  # 두 번째(기록용) 세션 생성에서 실패
            raise RuntimeError("db down")
        return fake_session

    monkeypatch.setattr(
        "dfm_bq_load_alerter.scheduler.jobs.sessionmaker_factory",
        MagicMock(return_value=failing_factory),
    )
    monkeypatch.setattr(
        "dfm_bq_load_alerter.scheduler.jobs.settings.job_timeout_seconds",
        0.05,
        raising=False,
    )

    async def slow_run_checks(*args, **kwargs):
        await asyncio.sleep(30)

    monkeypatch.setattr(
        "dfm_bq_load_alerter.scheduler.jobs.run_checks", slow_run_checks
    )

    await check_at("check-0800", time(8, 0))  # 예외가 나오면 테스트 실패

    assert "failed to record job-timeout event" in caplog.text
