"""dispatcher: per-group bucketing (PR-B)."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from dfm_bq_load_alerter.db.models import CheckStatus
from dfm_bq_load_alerter.notifier.dispatcher import DispatchSnapshot, dispatch

KST = ZoneInfo("Asia/Seoul")
NOW = datetime(2026, 5, 7, 9, 0, tzinfo=KST)


def _snap(
    status: CheckStatus,
    *,
    group_id: int | None = None,
    table: str = "T",
) -> DispatchSnapshot:
    return DispatchSnapshot(
        snapshot_id=1,
        dataset="bw",
        table_name=table,
        expected_check_time=NOW,
        actual_check_time=NOW,
        yesterday_row_count=1000,
        today_row_count=900,
        delta_percent_vs_yesterday=10.0,
        status=status,
        failure_reasons=["delta_exceeded"] if status == CheckStatus.fail else [],
        group_id=group_id,
    )


def _build_session(*, recipients_by_group: dict[int | None, list[str]]) -> MagicMock:
    """Mock AsyncSession that routes recipient queries by group_id.

    Webhook queries return [] for all groups (Teams not exercised here).
    """
    session = MagicMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    def execute_side_effect(stmt):
        result = MagicMock()
        text = str(stmt).lower()
        if "alert_recipients" in text:
            # Distinguish global vs per-group by presence of join table.
            if "alert_group_recipients" in text:
                params = stmt.compile().params  # type: ignore[attr-defined]
                gid = params.get("group_id_1")
                result.scalars.return_value.all.return_value = (
                    recipients_by_group.get(gid, [])
                )
            else:
                result.scalars.return_value.all.return_value = (
                    recipients_by_group.get(None, [])
                )
        else:
            # webhooks (any path) → empty
            result.scalars.return_value.all.return_value = []
        return result

    session.execute.side_effect = execute_side_effect
    return session


@pytest.mark.asyncio
async def test_per_group_bucketing_sends_one_email_per_bucket(monkeypatch) -> None:
    """Snapshots split across global + group=1 → two emails, one per bucket."""
    session = _build_session(
        recipients_by_group={None: ["global@example.com"], 1: ["g1@example.com"]}
    )
    sent_email = AsyncMock()
    monkeypatch.setattr(
        "dfm_bq_load_alerter.notifier.dispatcher.send_email", sent_email
    )

    snapshots = [
        _snap(CheckStatus.fail, group_id=None, table="A"),
        _snap(CheckStatus.fail, group_id=1, table="B"),
    ]
    sent = await dispatch(
        session, snapshots=snapshots, trigger_kind="check", expected=NOW, actual=NOW
    )

    assert sent_email.await_count == 2
    # Each call goes to the bucket's recipients only.
    awaits = sent_email.await_args_list
    to_lists = [call.kwargs["to"] for call in awaits]
    assert ["global@example.com"] in to_lists
    assert ["g1@example.com"] in to_lists
    assert sent == 2  # 2 email events


@pytest.mark.asyncio
async def test_bucket_with_no_fail_under_check_trigger_skipped(monkeypatch) -> None:
    """check trigger: a bucket whose snapshots are all OK is skipped, even
    when other buckets contain FAILs."""
    session = _build_session(
        recipients_by_group={None: ["global@example.com"], 1: ["g1@example.com"]}
    )
    sent_email = AsyncMock()
    monkeypatch.setattr(
        "dfm_bq_load_alerter.notifier.dispatcher.send_email", sent_email
    )

    snapshots = [
        _snap(CheckStatus.fail, group_id=None, table="A"),
        _snap(CheckStatus.ok, group_id=1, table="B"),
    ]
    await dispatch(
        session, snapshots=snapshots, trigger_kind="check", expected=NOW, actual=NOW
    )
    assert sent_email.await_count == 1
    # The OK group=1 bucket must not have been notified.
    awaits = sent_email.await_args_list
    assert ["g1@example.com"] not in [call.kwargs["to"] for call in awaits]


@pytest.mark.asyncio
async def test_report_trigger_sends_all_buckets_even_when_ok(monkeypatch) -> None:
    """report trigger: every bucket sends regardless of FAIL count."""
    session = _build_session(
        recipients_by_group={None: ["global@example.com"], 1: ["g1@example.com"]}
    )
    sent_email = AsyncMock()
    monkeypatch.setattr(
        "dfm_bq_load_alerter.notifier.dispatcher.send_email", sent_email
    )

    snapshots = [
        _snap(CheckStatus.ok, group_id=None, table="A"),
        _snap(CheckStatus.ok, group_id=1, table="B"),
    ]
    await dispatch(
        session, snapshots=snapshots, trigger_kind="report", expected=NOW, actual=NOW
    )
    assert sent_email.await_count == 2


@pytest.mark.asyncio
async def test_group_with_no_recipients_skips_email(monkeypatch) -> None:
    """A group with zero recipients: that bucket logs a skip but does not send."""
    session = _build_session(
        recipients_by_group={None: ["global@example.com"], 1: []}
    )
    sent_email = AsyncMock()
    monkeypatch.setattr(
        "dfm_bq_load_alerter.notifier.dispatcher.send_email", sent_email
    )

    snapshots = [
        _snap(CheckStatus.fail, group_id=None, table="A"),
        _snap(CheckStatus.fail, group_id=1, table="B"),
    ]
    sent = await dispatch(
        session, snapshots=snapshots, trigger_kind="check", expected=NOW, actual=NOW
    )
    # Only the global bucket sends an email; group=1 bucket has no recipients.
    assert sent_email.await_count == 1
    assert sent == 1
