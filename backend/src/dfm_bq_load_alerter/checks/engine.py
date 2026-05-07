from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from dfm_bq_load_alerter.bq.metadata import TableMetadata
from dfm_bq_load_alerter.db.models import CheckStatus, Frequency

KST = ZoneInfo("Asia/Seoul")


@dataclass(frozen=True, slots=True)
class CheckResult:
    """Pure evaluation outcome for a single (table, metadata, yesterday) tuple."""

    status: CheckStatus
    failure_reasons: list[str]
    delta_percent_vs_yesterday: float | None


def today_kst(now: datetime | None = None) -> date:
    """Return the current KST calendar date.

    Centralised so tests can freeze time consistently (rev 2 P8: Python
    zoneinfo is the single source of truth for date boundaries).
    """
    moment = now if now is not None else datetime.now(tz=KST)
    return moment.astimezone(KST).date()


def is_skip_for_monthly(
    frequency: Frequency, batch_day_of_month: int | None, today: date
) -> bool:
    """Monthly tables are only checked on their batch day."""
    if frequency != Frequency.monthly:
        return False
    if batch_day_of_month is None:
        return False
    return today.day != batch_day_of_month


def is_within_buffer(now: datetime, deadline_time: time) -> bool:
    """Return True when the current KST clock is still inside the buffer.

    Inside the buffer means **before** `deadline_time` on today's KST
    date. A pre-deadline check should not flag "not_updated_today" as a
    failure — the load may legitimately arrive any moment.
    """
    kst_now = now.astimezone(KST)
    today = kst_now.date()
    deadline = datetime.combine(today, deadline_time, tzinfo=KST)
    return kst_now < deadline


def evaluate(
    metadata: TableMetadata,
    *,
    yesterday_row_count: int | None,
    delta_threshold_percent: float,
    deadline_time: time | None = None,
    now: datetime | None = None,
) -> CheckResult:
    """Evaluate a single check against the spec's failure conditions.

    Failure if any of:
      1. last_modified is not today (KST) — **suppressed while still
         within the buffer** (now < deadline_time today). Once the
         deadline has passed the missing load becomes a real failure.
      2. row_count == 0 (always evaluated; "loaded but empty" is a fail
         even pre-deadline).
      3. |today - yesterday| / yesterday >= delta_threshold_percent / 100.
    INSUFFICIENT_HISTORY when (3) cannot be evaluated (no yesterday row)
    AND no other condition fired.
    """
    reasons: list[str] = []
    actual = now if now is not None else datetime.now(tz=KST)
    today = today_kst(actual)

    in_buffer = (
        deadline_time is not None and is_within_buffer(actual, deadline_time)
    )

    if metadata.last_modified is None and not in_buffer:
        reasons.append("missing_last_modified")
    elif (
        metadata.last_modified is not None
        and metadata.last_modified.astimezone(KST).date() != today
        and not in_buffer
    ):
        reasons.append("not_updated_today_kst")

    if metadata.row_count == 0:
        reasons.append("row_count_zero")

    delta_percent: float | None = None
    if yesterday_row_count is None:
        if not reasons:
            return CheckResult(
                status=CheckStatus.insufficient_history,
                failure_reasons=[],
                delta_percent_vs_yesterday=None,
            )
    elif yesterday_row_count > 0 and metadata.row_count is not None:
        delta = abs(metadata.row_count - yesterday_row_count)
        delta_percent = (delta / yesterday_row_count) * 100.0
        if delta_percent >= delta_threshold_percent:
            reasons.append(
                f"delta_exceeded:{delta_percent:.2f}%>={delta_threshold_percent:.2f}%"
            )
    elif yesterday_row_count == 0 and metadata.row_count and metadata.row_count > 0:
        delta_percent = float("inf")
        reasons.append(
            f"delta_exceeded:from_zero_to_{metadata.row_count}>="
            f"{delta_threshold_percent:.2f}%"
        )

    status = CheckStatus.fail if reasons else CheckStatus.ok
    return CheckResult(
        status=status,
        failure_reasons=reasons,
        delta_percent_vs_yesterday=(
            None
            if delta_percent is None or delta_percent == float("inf")
            else round(delta_percent, 2)
        ),
    )
