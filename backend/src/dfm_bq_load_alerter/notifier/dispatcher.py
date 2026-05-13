"""Bundle FAIL/INSUFFICIENT/OK rows into per-channel messages and send.

rev 2 M3: a single trigger's snapshots become **one message per channel**
(not one per table). FAIL >= 1 (trigger=check) or any (trigger=report)
results in a send. Result rows are persisted in `alert_events`.

rev 4 (그룹 제거): 모든 알람은 글로벌 단일 풀(active=true 인 수신자/Webhook
전체) 로만 송신된다. 테이블별 알람 조건은 `tables.cond_*` 로 유지된다.

This module is used both by the run-now API (PR-2 extension) and the
scheduler (PR-4). It is policy-aware (alert_policy.dedup_strategy) but
the v0.2.x default 'every-hour-resend' simply means: do not skip when
state is unchanged across triggers — every check that finds FAIL sends.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, time
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dfm_bq_load_alerter.db.models import (
    AlertEvent,
    AlertRecipient,
    Channel,
    CheckSnapshot,
    CheckStatus,
    EventStatus,
    Frequency,
    Table,
    TeamsWebhook,
    TriggerKind,
)
from dfm_bq_load_alerter.notifier.email import (
    EmailNotConfiguredError,
    send_email,
)
from dfm_bq_load_alerter.notifier.teams import TeamsPostError, post_teams_card
from dfm_bq_load_alerter.notifier.template import (
    TemplateRow,
    build_email_html,
    build_teams_cards,
)

log = logging.getLogger(__name__)


@dataclass(slots=True)
class DispatchSnapshot:
    """Lightweight projection of a CheckSnapshot enriched with table context.

    Decoupled from the ORM so tests can pass plain values without a DB.
    `note` / `today_last_modified` / `yesterday_last_modified` are PR-C
    enrichments shown in the alert body.
    """

    snapshot_id: int | None
    dataset: str
    table_name: str
    expected_check_time: datetime
    actual_check_time: datetime
    yesterday_row_count: int | None
    today_row_count: int | None
    delta_percent_vs_yesterday: float | None
    status: CheckStatus
    failure_reasons: list[str]
    note: str | None = None
    today_last_modified: datetime | None = None
    yesterday_last_modified: datetime | None = None
    project: str | None = None
    batch_time: time | None = None
    informational_notes: list[str] | None = None
    buffer_minutes: int | None = None


def _to_template_row(s: DispatchSnapshot) -> TemplateRow:
    return TemplateRow(
        dataset=s.dataset,
        table_name=s.table_name,
        expected_check_time=s.expected_check_time,
        actual_check_time=s.actual_check_time,
        yesterday_row_count=s.yesterday_row_count,
        today_row_count=s.today_row_count,
        delta_percent_vs_yesterday=s.delta_percent_vs_yesterday,
        status=s.status.value,
        failure_reasons=s.failure_reasons,
        note=s.note,
        today_last_modified=s.today_last_modified,
        yesterday_last_modified=s.yesterday_last_modified,
        project=s.project,
        batch_time=s.batch_time,
        informational_notes=list(s.informational_notes or []),
        buffer_minutes=s.buffer_minutes,
    )


async def _get_active_recipients(session: AsyncSession) -> list[str]:
    rows = (
        await session.execute(
            select(AlertRecipient.email).where(AlertRecipient.active.is_(True))
        )
    ).scalars().all()
    return list(rows)


async def _get_active_webhooks(session: AsyncSession) -> list[TeamsWebhook]:
    rows = (
        await session.execute(
            select(TeamsWebhook).where(TeamsWebhook.active.is_(True))
        )
    ).scalars().all()
    return list(rows)


async def _resolve_webhook_url(hook: TeamsWebhook) -> str:
    return hook.webhook_url or ""


async def _persist_event(
    session: AsyncSession,
    *,
    snapshot_id: int | None,
    trigger_kind: TriggerKind,
    channel: Channel,
    status: EventStatus,
    payload_summary: str,
    error: str | None = None,
) -> None:
    session.add(
        AlertEvent(
            snapshot_id=snapshot_id,
            trigger_kind=trigger_kind,
            channel=channel,
            status=status,
            payload_summary=payload_summary,
            error=error,
        )
    )


async def dispatch(
    session: AsyncSession,
    *,
    snapshots: list[DispatchSnapshot],
    trigger_kind: Literal["check", "report"],
    expected: datetime,
    actual: datetime,
) -> int:
    """Send one bundled message to the global recipient/webhook pool.

    Returns the total number of `alert_events` rows added (sent + failed + skipped).
    """
    if not snapshots and trigger_kind == "report":
        log.info("dispatch skipped: empty snapshot list for trigger=report")
        return 0
    fail_count = sum(1 for s in snapshots if s.status == CheckStatus.fail)
    if trigger_kind == "check" and fail_count == 0:
        log.info("dispatch skipped: no FAIL rows for trigger=check")
        return 0

    rows = [_to_template_row(s) for s in snapshots]
    subject, html = build_email_html(
        trigger_kind=trigger_kind, expected=expected, actual=actual, rows=rows
    )
    # Teams Webhook 페이로드 한계 회피를 위해 카드 N 분할 가능.
    teams_cards = build_teams_cards(
        trigger_kind=trigger_kind, expected=expected, actual=actual, rows=rows
    )

    summary = f"{trigger_kind} · fail={fail_count}/{len(snapshots)}"
    tk_enum = TriggerKind.check if trigger_kind == "check" else TriggerKind.report
    snapshot_id = snapshots[0].snapshot_id if snapshots else None
    events_added = 0

    # Email
    recipients = await _get_active_recipients(session)
    if recipients:
        try:
            await send_email(to=recipients, subject=subject, html=html)
            await _persist_event(
                session,
                snapshot_id=snapshot_id,
                trigger_kind=tk_enum,
                channel=Channel.email,
                status=EventStatus.sent,
                payload_summary=summary,
            )
        except EmailNotConfiguredError as exc:
            log.warning("email channel disabled: %s", exc)
            await _persist_event(
                session,
                snapshot_id=snapshot_id,
                trigger_kind=tk_enum,
                channel=Channel.email,
                status=EventStatus.skipped,
                payload_summary=summary,
                error=str(exc),
            )
        except Exception as exc:  # noqa: BLE001 — record and continue
            log.exception("email send failed")
            await _persist_event(
                session,
                snapshot_id=snapshot_id,
                trigger_kind=tk_enum,
                channel=Channel.email,
                status=EventStatus.failed,
                payload_summary=summary,
                error=f"{type(exc).__name__}: {exc}",
            )
        events_added += 1
    else:
        log.info("no active recipients; email skipped")

    # Teams
    webhooks = await _get_active_webhooks(session)
    for hook in webhooks:
        url = await _resolve_webhook_url(hook)
        if not url:
            await _persist_event(
                session,
                snapshot_id=snapshot_id,
                trigger_kind=tk_enum,
                channel=Channel.teams,
                status=EventStatus.skipped,
                payload_summary=f"{summary} · webhook={hook.name}",
                error="webhook_url is empty",
            )
            events_added += 1
            continue
        chunk_total = len(teams_cards)
        chunk_summary = (
            f"{summary} · webhook={hook.name}"
            + (f" · chunks={chunk_total}" if chunk_total > 1 else "")
        )
        try:
            for idx, card in enumerate(teams_cards, start=1):
                log.info(
                    "teams chunk %d/%d webhook=%s", idx, chunk_total, hook.name
                )
                await post_teams_card(webhook_url=url, payload=card)
            await _persist_event(
                session,
                snapshot_id=snapshot_id,
                trigger_kind=tk_enum,
                channel=Channel.teams,
                status=EventStatus.sent,
                payload_summary=chunk_summary,
            )
        except TeamsPostError as exc:
            log.warning("teams webhook failed: %s", exc)
            await _persist_event(
                session,
                snapshot_id=snapshot_id,
                trigger_kind=tk_enum,
                channel=Channel.teams,
                status=EventStatus.failed,
                payload_summary=chunk_summary,
                error=str(exc),
            )
        events_added += 1

    await session.flush()
    return events_added


async def _lookup_baseline_snapshot(
    session: AsyncSession,
    *,
    table_id: int,
    frequency: Frequency,
    today_in_kst: datetime,
) -> CheckSnapshot | None:
    """Most recent baseline snapshot — yesterday for daily, prev month for monthly.

    Mirrors `checks.runner._baseline_snapshot` but returns the full
    snapshot so the template can render `row_count` and `last_modified`.
    """
    from datetime import timedelta
    from zoneinfo import ZoneInfo

    from dfm_bq_load_alerter.checks.runner import _previous_month_window

    kst = ZoneInfo("Asia/Seoul")
    today = today_in_kst.astimezone(kst).date()
    if frequency == Frequency.monthly:
        start, end = _previous_month_window(today)
    else:
        yesterday = today - timedelta(days=1)
        start = datetime.combine(yesterday, datetime.min.time(), tzinfo=kst)
        end = datetime.combine(today, datetime.min.time(), tzinfo=kst)
    stmt = (
        select(CheckSnapshot)
        .where(CheckSnapshot.table_id == table_id)
        .where(CheckSnapshot.checked_at >= start)
        .where(CheckSnapshot.checked_at < end)
        .where(CheckSnapshot.status != CheckStatus.insufficient_history)
        .order_by(CheckSnapshot.checked_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def build_dispatch_snapshots(
    session: AsyncSession, snapshots: list[CheckSnapshot]
) -> list[DispatchSnapshot]:
    """Enrich ORM snapshots with table info, yesterday row/time, and note."""
    if not snapshots:
        return []

    from dfm_bq_load_alerter.db.models import AlertPolicy
    from dfm_bq_load_alerter.settings import settings

    fallback_project = settings.bq_project_id or None

    policy = await session.get(AlertPolicy, 1)
    fallback_buffer = policy.default_buffer_minutes if policy is not None else 30

    table_ids = {s.table_id for s in snapshots}
    tables = (
        await session.execute(select(Table).where(Table.id.in_(table_ids)))
    ).scalars().all()
    table_map = {t.id: t for t in tables}

    result: list[DispatchSnapshot] = []
    for s in snapshots:
        table = table_map.get(s.table_id)
        if table is None:
            continue
        yday = await _lookup_baseline_snapshot(
            session,
            table_id=table.id,
            frequency=table.frequency,
            today_in_kst=s.checked_at,
        )
        result.append(
            DispatchSnapshot(
                snapshot_id=s.id,
                dataset=table.dataset,
                table_name=table.table_name,
                expected_check_time=s.expected_check_time,
                actual_check_time=s.checked_at,
                yesterday_row_count=yday.row_count if yday else None,
                today_row_count=s.row_count,
                delta_percent_vs_yesterday=(
                    float(s.delta_percent_vs_yesterday)
                    if s.delta_percent_vs_yesterday is not None
                    else None
                ),
                status=s.status,
                failure_reasons=list(s.failure_reasons or []),
                note=table.note,
                today_last_modified=s.last_modified,
                yesterday_last_modified=yday.last_modified if yday else None,
                project=table.project_id or fallback_project,
                batch_time=table.batch_time,
                informational_notes=list(s.informational_notes or []),
                buffer_minutes=(
                    table.buffer_minutes
                    if table.buffer_minutes is not None
                    else fallback_buffer
                ),
            )
        )
    return result
