"""Bundle FAIL/INSUFFICIENT/OK rows into per-channel messages and send.

rev 2 M3: a single trigger's snapshots become **one message per channel**
(not one per table). FAIL >= 1 (trigger=check) or any (trigger=report)
results in a send. Result rows are persisted in `alert_events`.

This module is used both by the run-now API (PR-2 extension) and the
scheduler (PR-4). It is policy-aware (alert_policy.dedup_strategy) but
the v0.2.x default 'every-hour-resend' simply means: do not skip when
state is unchanged across triggers — every check that finds FAIL sends.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
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
    build_teams_card,
)
from dfm_bq_load_alerter.settings import settings

log = logging.getLogger(__name__)


@dataclass(slots=True)
class DispatchSnapshot:
    """Lightweight projection of a CheckSnapshot enriched with table context.

    Decoupled from the ORM so tests can pass plain values without a DB.
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
    )


async def _get_recipients(session: AsyncSession) -> list[str]:
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


async def _resolve_webhook_url(secret_ref: str) -> str:
    """Read webhook URL from K8s Secret reference. v0.2.x minimal implementation
    falls back to env DFM_ALERT_TEAMS_WEBHOOK_<secret_ref> for local dev/testing.

    Production wiring: K8s ServiceAccount has Role to read Secret in same ns
    (rev 2 P6). Implemented in PR-5 alongside webhook auto-create on POST.
    """
    import os

    env_key = f"DFM_ALERT_TEAMS_WEBHOOK_{secret_ref.upper().replace('-', '_')}"
    return os.environ.get(env_key, "")


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
    """Send per-channel bundled messages and persist alert_events rows.

    Returns the number of `alert_events` rows added (sent + failed + skipped).
    """
    fail_count = sum(1 for s in snapshots if s.status == CheckStatus.fail)
    if trigger_kind == "check" and fail_count == 0:
        log.info("dispatch skipped: no FAIL rows for trigger=check")
        return 0
    if not snapshots and trigger_kind == "report":
        log.info("dispatch skipped: empty snapshot list for trigger=report")
        return 0

    rows = [_to_template_row(s) for s in snapshots]
    subject, html = build_email_html(
        trigger_kind=trigger_kind, expected=expected, actual=actual, rows=rows
    )
    teams_card = build_teams_card(
        trigger_kind=trigger_kind, expected=expected, actual=actual, rows=rows
    )

    summary = f"{trigger_kind} · fail={fail_count}/{len(snapshots)}"
    tk_enum = TriggerKind.check if trigger_kind == "check" else TriggerKind.report
    snapshot_id = snapshots[0].snapshot_id if snapshots else None
    events_added = 0

    # Email
    recipients = await _get_recipients(session)
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
        log.info("no active alert_recipients; email channel skipped")

    # Teams
    webhooks = await _get_active_webhooks(session)
    if not webhooks and settings.teams_default_webhook_secret_ref:
        webhooks = [
            TeamsWebhook(
                id=0,
                name="default",
                secret_ref=settings.teams_default_webhook_secret_ref,
                active=True,
            )
        ]

    for hook in webhooks:
        url = await _resolve_webhook_url(hook.secret_ref)
        if not url:
            await _persist_event(
                session,
                snapshot_id=snapshot_id,
                trigger_kind=tk_enum,
                channel=Channel.teams,
                status=EventStatus.skipped,
                payload_summary=f"{summary} · webhook={hook.name}",
                error=f"secret {hook.secret_ref} not resolvable",
            )
            events_added += 1
            continue
        try:
            await post_teams_card(webhook_url=url, payload=teams_card)
            await _persist_event(
                session,
                snapshot_id=snapshot_id,
                trigger_kind=tk_enum,
                channel=Channel.teams,
                status=EventStatus.sent,
                payload_summary=f"{summary} · webhook={hook.name}",
            )
        except TeamsPostError as exc:
            log.warning("teams webhook failed: %s", exc)
            await _persist_event(
                session,
                snapshot_id=snapshot_id,
                trigger_kind=tk_enum,
                channel=Channel.teams,
                status=EventStatus.failed,
                payload_summary=f"{summary} · webhook={hook.name}",
                error=str(exc),
            )
        events_added += 1

    await session.flush()
    return events_added


async def build_dispatch_snapshots(
    session: AsyncSession, snapshots: list[CheckSnapshot]
) -> list[DispatchSnapshot]:
    """Enrich ORM snapshots with table info and yesterday row_count."""
    if not snapshots:
        return []

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
        # yesterday lookup is intentionally light here (use snapshot's own
        # delta_percent which already reflects yesterday). Keeping the
        # template field nullable lets us avoid an extra round-trip.
        result.append(
            DispatchSnapshot(
                snapshot_id=s.id,
                dataset=table.dataset,
                table_name=table.table_name,
                expected_check_time=s.expected_check_time,
                actual_check_time=s.checked_at,
                yesterday_row_count=None,
                today_row_count=s.row_count,
                delta_percent_vs_yesterday=(
                    float(s.delta_percent_vs_yesterday)
                    if s.delta_percent_vs_yesterday is not None
                    else None
                ),
                status=s.status,
                failure_reasons=list(s.failure_reasons or []),
            )
        )
    return result
