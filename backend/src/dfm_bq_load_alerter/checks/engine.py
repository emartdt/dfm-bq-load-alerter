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


def _inflow_drift_minutes(
    today_lm: datetime, baseline_lm: datetime
) -> int:
    """Difference (in minutes) between two clock-times-of-day, ignoring date.

    The check answers: 평소(baseline) 보다 오늘 적재가 얼마나 늦었는가?
    Negative result = today loaded *earlier* than the baseline; we still
    want to surface that as |minutes| so the threshold catches both
    early and late drift.
    """
    today_min = today_lm.astimezone(KST).hour * 60 + today_lm.astimezone(KST).minute
    base_min = (
        baseline_lm.astimezone(KST).hour * 60 + baseline_lm.astimezone(KST).minute
    )
    return abs(today_min - base_min)


def evaluate(
    metadata: TableMetadata,
    *,
    yesterday_row_count: int | None,
    delta_threshold_percent: float,
    deadline_time: time | None = None,
    now: datetime | None = None,
    cond_buffer_load: bool = True,
    cond_delta_rowcount: bool = True,
    cond_inflow_time_drift: bool = False,
    inflow_drift_threshold_minutes: int | None = None,
    baseline_last_modified: datetime | None = None,
) -> CheckResult:
    """Evaluate a single check against the configured failure conditions.

    Conditions are toggleable per-table (요구사항: "조건 종류 (OR로
    설정 가능)").

    - `cond_buffer_load` (default on): not-updated-today (deadline aware)
      AND row_count==0.
    - `cond_delta_rowcount` (default on): |today - baseline| / baseline
      >= delta_threshold_percent / 100. Baseline is yesterday for daily
      and last-month for monthly tables (caller-controlled via
      `yesterday_row_count`; the parameter name is historical).
    - `cond_inflow_time_drift` (default off): clock-time-of-day diff
      between today's last_modified and the baseline_last_modified;
      fail when |diff| >= threshold (minutes).

    INSUFFICIENT_HISTORY when delta cannot be evaluated and no other
    condition fired.
    """
    reasons: list[str] = []
    actual = now if now is not None else datetime.now(tz=KST)
    today = today_kst(actual)

    in_buffer = (
        deadline_time is not None and is_within_buffer(actual, deadline_time)
    )

    if cond_buffer_load:
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
    if cond_delta_rowcount:
        if yesterday_row_count is None:
            if not reasons:
                # Insufficient history wins only when no other check fired.
                pass
        elif yesterday_row_count > 0 and metadata.row_count is not None:
            delta = abs(metadata.row_count - yesterday_row_count)
            delta_percent = (delta / yesterday_row_count) * 100.0
            if delta_percent >= delta_threshold_percent:
                reasons.append(
                    f"delta_exceeded:{delta_percent:.2f}%>="
                    f"{delta_threshold_percent:.2f}%"
                )
        elif (
            yesterday_row_count == 0
            and metadata.row_count
            and metadata.row_count > 0
        ):
            delta_percent = float("inf")
            reasons.append(
                f"delta_exceeded:from_zero_to_{metadata.row_count}>="
                f"{delta_threshold_percent:.2f}%"
            )

    if (
        cond_inflow_time_drift
        and metadata.last_modified is not None
        and baseline_last_modified is not None
        and inflow_drift_threshold_minutes is not None
    ):
        drift = _inflow_drift_minutes(metadata.last_modified, baseline_last_modified)
        if drift >= inflow_drift_threshold_minutes:
            reasons.append(
                f"inflow_drift:{drift}m>={inflow_drift_threshold_minutes}m"
            )

    # INSUFFICIENT_HISTORY only when delta path was the only thing missing
    # and no other condition fired.
    if (
        not reasons
        and cond_delta_rowcount
        and yesterday_row_count is None
    ):
        return CheckResult(
            status=CheckStatus.insufficient_history,
            failure_reasons=[],
            delta_percent_vs_yesterday=None,
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
