from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
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


def is_within_buffer(now: datetime, batch_time: time, buffer_minutes: int) -> bool:
    """Return True when the current KST clock is still inside the buffer window.

    Window end = `batch_time + buffer_minutes` (today, KST). A pre-window-end
    check should not flag "not_updated_today" as a failure — the load may
    legitimately arrive any moment.
    """
    kst_now = now.astimezone(KST)
    today = kst_now.date()
    window_start = datetime.combine(today, batch_time, tzinfo=KST)
    window_end = window_start + timedelta(minutes=buffer_minutes)
    return kst_now < window_end


def evaluate(
    metadata: TableMetadata,
    *,
    yesterday_row_count: int | None,
    delta_threshold_percent: float,
    batch_time: time | None = None,
    buffer_minutes: int | None = None,
    now: datetime | None = None,
    cond_buffer_load: bool = True,
    cond_delta_rowcount: bool = True,
) -> CheckResult:
    """Evaluate a single check against the configured failure conditions.

    FAIL 조건 (OR):
    - `cond_buffer_load`: 윈도우(batch_time + buffer_minutes) 밖에서
      미적재(last_modified 없음/오늘이 아님) → FAIL. 그리고 row_count==0 이면
      윈도우와 무관하게 FAIL.
    - `cond_delta_rowcount`: |today - baseline| / baseline
      >= delta_threshold_percent / 100. Baseline 은 daily=어제, monthly=전월.
      Baseline 이 없으면 증감률 비교를 생략하고 사유에 그 사실을 남긴다(FAIL 아님).
    """
    reasons: list[str] = []
    notes: list[str] = []
    actual = now if now is not None else datetime.now(tz=KST)
    today = today_kst(actual)

    # 버퍼 시간 내 여부
    in_buffer = (
        batch_time is not None
        and buffer_minutes is not None
        and is_within_buffer(actual, batch_time, buffer_minutes)
    )

    if cond_buffer_load:
        if metadata.last_modified is None and not in_buffer:
            reasons.append("최종 업데이트 시각 없음")
        elif (
            metadata.last_modified is not None
            and metadata.last_modified.astimezone(KST).date() != today
            and not in_buffer
        ):
            reasons.append("오늘 미적재")

        if metadata.row_count == 0:
            reasons.append("row count 0")

    delta_percent: float | None = None
    if cond_delta_rowcount:
        if yesterday_row_count is None:
            notes.append("이전 배치 기록 없음 - 증감률 비교 생략")
        elif yesterday_row_count > 0 and metadata.row_count is not None:
            delta = abs(metadata.row_count - yesterday_row_count)
            delta_percent = (delta / yesterday_row_count) * 100.0
            if delta_percent >= delta_threshold_percent:
                reasons.append(
                    f"증감률 임계치 초과: {delta_percent:.2f}% >= "
                    f"{delta_threshold_percent:.2f}%"
                )
        elif (
            yesterday_row_count == 0
            and metadata.row_count
            and metadata.row_count > 0
        ):
            delta_percent = float("inf")
            reasons.append(
                f"0 → {metadata.row_count} 급증 "
                f"(임계치 {delta_threshold_percent:.2f}%)"
            )

    status = CheckStatus.fail if reasons else CheckStatus.ok
    return CheckResult(
        status=status,
        failure_reasons=reasons + notes,
        delta_percent_vs_yesterday=(
            None
            if delta_percent is None or delta_percent == float("inf")
            else round(delta_percent, 2)
        ),
    )
