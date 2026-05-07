"""Bundle FAIL/INSUFFICIENT/OK rows into per-channel messages and send.

rev 2 M3: a single trigger's snapshots become **one message per channel**
(not one per table). FAIL >= 1 (trigger=check) or any (trigger=report)
results in a send. Result rows are persisted in `alert_events`.

rev 3 (PR-B): snapshots are bucketed by `table.group_id` first. Each
bucket sends to its group's channels (or the global default channels
when `group_id IS NULL`). This implements 요구사항의 "그룹별로 알람
채널 설정 가능" — a table assigned to a group only notifies that
group's recipients/webhooks.

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
    AlertGroupRecipient,
    AlertGroupWebhook,
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

log = logging.getLogger(__name__)


@dataclass(slots=True)
class DispatchSnapshot:
    """Lightweight projection of a CheckSnapshot enriched with table context.

    Decoupled from the ORM so tests can pass plain values without a DB.
    `group_id` drives per-group channel routing (PR-B).
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
    group_id: int | None = None


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


async def _get_recipients_for_group(
    session: AsyncSession, group_id: int | None
) -> list[str]:
    """group_id IS NULL → 글로벌 active 수신자 전부 / 아니면 그룹 멤버만."""
    if group_id is None:
        stmt = select(AlertRecipient.email).where(AlertRecipient.active.is_(True))
    else:
        stmt = (
            select(AlertRecipient.email)
            .join(
                AlertGroupRecipient,
                AlertGroupRecipient.recipient_id == AlertRecipient.id,
            )
            .where(AlertGroupRecipient.group_id == group_id)
            .where(AlertRecipient.active.is_(True))
        )
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


async def _get_webhooks_for_group(
    session: AsyncSession, group_id: int | None
) -> list[TeamsWebhook]:
    if group_id is None:
        stmt = select(TeamsWebhook).where(TeamsWebhook.active.is_(True))
    else:
        stmt = (
            select(TeamsWebhook)
            .join(
                AlertGroupWebhook,
                AlertGroupWebhook.webhook_id == TeamsWebhook.id,
            )
            .where(AlertGroupWebhook.group_id == group_id)
            .where(TeamsWebhook.active.is_(True))
        )
    rows = (await session.execute(stmt)).scalars().all()
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


async def _dispatch_bucket(
    session: AsyncSession,
    *,
    bucket_snapshots: list[DispatchSnapshot],
    group_id: int | None,
    trigger_kind: Literal["check", "report"],
    expected: datetime,
    actual: datetime,
) -> int:
    """그룹 한 개 버킷에 대해 채널별 묶음 송신 및 AlertEvent 적재.

    호출 시점에 trigger_kind=='check' AND fail_count==0 여부는 호출자가
    이미 필터링한다. 본 함수는 무조건 송신을 수행한다.
    """
    fail_count = sum(1 for s in bucket_snapshots if s.status == CheckStatus.fail)
    rows = [_to_template_row(s) for s in bucket_snapshots]
    subject, html = build_email_html(
        trigger_kind=trigger_kind, expected=expected, actual=actual, rows=rows
    )
    teams_card = build_teams_card(
        trigger_kind=trigger_kind, expected=expected, actual=actual, rows=rows
    )

    bucket_label = f"group={group_id}" if group_id is not None else "group=global"
    summary = (
        f"{trigger_kind} · {bucket_label} · "
        f"fail={fail_count}/{len(bucket_snapshots)}"
    )
    tk_enum = TriggerKind.check if trigger_kind == "check" else TriggerKind.report
    snapshot_id = bucket_snapshots[0].snapshot_id if bucket_snapshots else None
    events_added = 0

    # Email
    recipients = await _get_recipients_for_group(session, group_id)
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
            log.exception("email send failed (%s)", bucket_label)
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
        log.info("no recipients for %s; email skipped", bucket_label)

    # Teams
    webhooks = await _get_webhooks_for_group(session, group_id)
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
            log.warning("teams webhook failed (%s): %s", bucket_label, exc)
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

    return events_added


async def dispatch(
    session: AsyncSession,
    *,
    snapshots: list[DispatchSnapshot],
    trigger_kind: Literal["check", "report"],
    expected: datetime,
    actual: datetime,
) -> int:
    """Bucket snapshots by group_id and dispatch each bucket separately.

    Returns the total number of `alert_events` rows added across all
    buckets (sent + failed + skipped).
    """
    if not snapshots and trigger_kind == "report":
        log.info("dispatch skipped: empty snapshot list for trigger=report")
        return 0
    if trigger_kind == "check":
        total_fail = sum(1 for s in snapshots if s.status == CheckStatus.fail)
        if total_fail == 0:
            log.info("dispatch skipped: no FAIL rows for trigger=check")
            return 0

    # Stable bucket order: None (global) first, then ascending group_id.
    buckets: dict[int | None, list[DispatchSnapshot]] = {}
    for s in snapshots:
        buckets.setdefault(s.group_id, []).append(s)
    ordered_keys = sorted(
        buckets.keys(), key=lambda k: (0, 0) if k is None else (1, k)
    )

    events_added = 0
    for group_id in ordered_keys:
        bucket = buckets[group_id]
        if trigger_kind == "check" and not any(
            s.status == CheckStatus.fail for s in bucket
        ):
            log.info(
                "dispatch: skip bucket group=%s (no FAIL in bucket)", group_id
            )
            continue
        events_added += await _dispatch_bucket(
            session,
            bucket_snapshots=bucket,
            group_id=group_id,
            trigger_kind=trigger_kind,
            expected=expected,
            actual=actual,
        )

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
                group_id=table.group_id,
            )
        )
    return result
