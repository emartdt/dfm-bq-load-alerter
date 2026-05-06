"""Tests for the scheduler job functions (check_at, report_745).

These verify that the job composes the expected/actual datetime correctly
and dispatches with the right trigger_kind. The DB session and dispatcher
are mocked so no PG/SMTP/Teams is needed.
"""
from __future__ import annotations

from datetime import datetime, time
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time

from dfm_bq_load_alerter.scheduler.jobs import (
    _expected_check_datetime,
    check_at,
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
