"""Unit tests for the notifier dispatcher.

These tests focus on the bundling/skip semantics (rev 2 M3) and on
recording AlertEvent rows. The DB session is mocked so no PG is needed.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from dfm_bq_load_alerter.db.models import (
    AlertEvent,
    CheckStatus,
    EventStatus,
)
from dfm_bq_load_alerter.notifier.dispatcher import DispatchSnapshot, dispatch
from dfm_bq_load_alerter.notifier.email import EmailNotConfiguredError

KST = ZoneInfo("Asia/Seoul")
NOW = datetime(2026, 5, 6, 9, 0, tzinfo=KST)


def _snap(status: CheckStatus, *, dataset="bw", table="PZEVENTID") -> DispatchSnapshot:
    return DispatchSnapshot(
        snapshot_id=1,
        dataset=dataset,
        table_name=table,
        expected_check_time=NOW,
        actual_check_time=NOW,
        yesterday_row_count=1000,
        today_row_count=900,
        delta_percent_vs_yesterday=10.0,
        status=status,
        failure_reasons=["delta_exceeded"] if status == CheckStatus.fail else [],
    )


def _build_session(*, recipients: list[str], webhooks=None) -> MagicMock:
    """Construct an AsyncSession mock that yields canned recipient/webhook rows."""
    session = MagicMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    def execute_side_effect(stmt):
        result = MagicMock()
        text = str(stmt)
        if "alert_recipients" in text:
            result.scalars.return_value.all.return_value = recipients
        elif "teams_webhooks" in text:
            result.scalars.return_value.all.return_value = list(webhooks or [])
        else:
            result.scalars.return_value.all.return_value = []
        return result

    session.execute.side_effect = execute_side_effect
    return session


@pytest.mark.asyncio
async def test_check_trigger_skips_when_no_fail() -> None:
    session = _build_session(recipients=["a@example.com"])
    sent = await dispatch(
        session,
        snapshots=[_snap(CheckStatus.ok)],
        trigger_kind="check",
        expected=NOW,
        actual=NOW,
    )
    assert sent == 0
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_check_trigger_sends_when_fail_present(monkeypatch) -> None:
    """1 FAIL → 1 email event (no Teams webhook configured)."""
    session = _build_session(recipients=["a@example.com"])

    sent_email = AsyncMock()
    monkeypatch.setattr(
        "dfm_bq_load_alerter.notifier.dispatcher.send_email", sent_email
    )

    sent = await dispatch(
        session,
        snapshots=[_snap(CheckStatus.fail)],
        trigger_kind="check",
        expected=NOW,
        actual=NOW,
    )
    assert sent == 1
    sent_email.assert_awaited_once()
    added = session.add.call_args_list
    assert len(added) == 1
    event: AlertEvent = added[0][0][0]
    assert event.channel.value == "email"
    assert event.status == EventStatus.sent


@pytest.mark.asyncio
async def test_email_skipped_when_smtp_not_configured(monkeypatch) -> None:
    session = _build_session(recipients=["a@example.com"])

    async def boom(**_kwargs):
        raise EmailNotConfiguredError("smtp not set")

    monkeypatch.setattr("dfm_bq_load_alerter.notifier.dispatcher.send_email", boom)

    sent = await dispatch(
        session,
        snapshots=[_snap(CheckStatus.fail)],
        trigger_kind="check",
        expected=NOW,
        actual=NOW,
    )
    assert sent == 1
    event: AlertEvent = session.add.call_args_list[0][0][0]
    assert event.status == EventStatus.skipped


@pytest.mark.asyncio
async def test_check_trigger_bundles_n_fails_into_one_email(monkeypatch) -> None:
    """N FAIL rows → still ONE email (channel-bundled). rev 2 M3."""
    session = _build_session(recipients=["a@example.com"])

    sent_email = AsyncMock()
    monkeypatch.setattr(
        "dfm_bq_load_alerter.notifier.dispatcher.send_email", sent_email
    )

    snapshots = [
        _snap(CheckStatus.fail, table=f"T{i:02d}") for i in range(29)
    ]
    sent = await dispatch(
        session,
        snapshots=snapshots,
        trigger_kind="check",
        expected=NOW,
        actual=NOW,
    )
    assert sent == 1
    assert sent_email.await_count == 1


@pytest.mark.asyncio
async def test_report_trigger_sends_even_when_all_ok(monkeypatch) -> None:
    session = _build_session(recipients=["a@example.com"])

    sent_email = AsyncMock()
    monkeypatch.setattr(
        "dfm_bq_load_alerter.notifier.dispatcher.send_email", sent_email
    )

    sent = await dispatch(
        session,
        snapshots=[_snap(CheckStatus.ok)],
        trigger_kind="report",
        expected=NOW,
        actual=NOW,
    )
    assert sent == 1
    sent_email.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_trigger_excludes_skip_rows(monkeypatch) -> None:
    """점검(check) 알림: SKIP 스냅샷은 본문에서 제외되어야 하고,
    FAIL 0건이면 발송 자체를 건너뛴다."""
    session = _build_session(recipients=["a@example.com"])
    sent_email = AsyncMock()
    monkeypatch.setattr(
        "dfm_bq_load_alerter.notifier.dispatcher.send_email", sent_email
    )

    sent = await dispatch(
        session,
        snapshots=[_snap(CheckStatus.skip)],
        trigger_kind="check",
        expected=NOW,
        actual=NOW,
    )
    assert sent == 0
    sent_email.assert_not_awaited()
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_check_trigger_skip_does_not_leak_into_fail_email(monkeypatch) -> None:
    """점검 알림: FAIL 1건 + SKIP 1건 → 이메일은 발송되지만 본문 HTML 에는
    SKIP 카드가 포함되지 않아야 한다."""
    session = _build_session(recipients=["a@example.com"])
    captured: dict[str, str] = {}

    async def fake_send_email(*, to, subject, html):
        captured["html"] = html

    monkeypatch.setattr(
        "dfm_bq_load_alerter.notifier.dispatcher.send_email", fake_send_email
    )

    sent = await dispatch(
        session,
        snapshots=[
            _snap(CheckStatus.fail, table="FAIL_T"),
            _snap(CheckStatus.skip, table="SKIP_T"),
        ],
        trigger_kind="check",
        expected=NOW,
        actual=NOW,
    )
    assert sent == 1
    assert "FAIL_T" in captured["html"]
    assert "SKIP_T" not in captured["html"]
    assert "SKIP" not in captured["html"]


@pytest.mark.asyncio
async def test_report_trigger_includes_skip_rows(monkeypatch) -> None:
    """일일 리포트(report): SKIP 스냅샷도 본문에 SKIP 섹션으로 노출된다."""
    session = _build_session(recipients=["a@example.com"])
    captured: dict[str, str] = {}

    async def fake_send_email(*, to, subject, html):
        captured["html"] = html

    monkeypatch.setattr(
        "dfm_bq_load_alerter.notifier.dispatcher.send_email", fake_send_email
    )

    sent = await dispatch(
        session,
        snapshots=[
            _snap(CheckStatus.ok, table="OK_T"),
            _snap(CheckStatus.skip, table="SKIP_T"),
        ],
        trigger_kind="report",
        expected=NOW,
        actual=NOW,
    )
    assert sent == 1
    assert "SKIP_T" in captured["html"]
    assert "SKIP (1)" in captured["html"]
    assert "OK_T" in captured["html"]


@pytest.mark.asyncio
async def test_dispatch_does_not_send_when_no_recipients(monkeypatch) -> None:
    """Empty recipient list → no email send and no AlertEvent row."""
    session = _build_session(recipients=[])
    sent_email = AsyncMock()
    monkeypatch.setattr(
        "dfm_bq_load_alerter.notifier.dispatcher.send_email", sent_email
    )

    sent = await dispatch(
        session,
        snapshots=[_snap(CheckStatus.fail)],
        trigger_kind="check",
        expected=NOW,
        actual=NOW,
    )
    assert sent == 0
    sent_email.assert_not_awaited()
    session.add.assert_not_called()
