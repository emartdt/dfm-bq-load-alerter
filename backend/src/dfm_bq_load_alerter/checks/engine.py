from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from dfm_bq_load_alerter.bq.metadata import TableMetadata
from dfm_bq_load_alerter.db.models import CheckStatus, Frequency

KST = ZoneInfo("Asia/Seoul")


@dataclass(frozen=True, slots=True)
class CheckResult:
    """Pure evaluation outcome for a single (table, metadata, yesterday) tuple.

    ``failure_reasons`` 는 FAIL 판정을 유발한 조건들이며, ``informational_notes`` 는
    FAIL 과 무관한 운영 안내(예: 이전 배치 기록 부재로 증감률 비교를 생략) 다.
    두 필드는 알람 템플릿에서도 색상/아이콘으로 구분 렌더된다.
    """

    status: CheckStatus
    failure_reasons: list[str]
    delta_percent_vs_yesterday: float | None
    informational_notes: list[str]


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


def buffer_window(
    now: datetime, batch_time: time, buffer_minutes: int
) -> tuple[datetime, datetime]:
    """Return today's symmetric buffer window in KST: ``[start, end]``.

    Window = ``[batch_time - buffer_minutes, batch_time + buffer_minutes]``,
    anchored to ``now`` 의 KST 달력 날짜. 적재가 이 구간 안에서 일어나야
    "정상 적재"로 간주된다 (엄격 해석).
    """
    today = now.astimezone(KST).date()
    anchor = datetime.combine(today, batch_time, tzinfo=KST)
    delta = timedelta(minutes=buffer_minutes)
    return anchor - delta, anchor + delta


def is_within_buffer(now: datetime, batch_time: time, buffer_minutes: int) -> bool:
    """Return True while the current KST clock is still before the window end.

    Window end = ``batch_time + buffer_minutes`` (today, KST) — the latest
    moment a load is still expected. Pre-window-end 검증은 적재가 곧 도착할
    가능성이 있으므로 FAIL 로 단정하지 않는다.
    """
    _, window_end = buffer_window(now, batch_time, buffer_minutes)
    return now.astimezone(KST) < window_end


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
    - `cond_buffer_load`: 윈도우 ``[batch_time - buffer, batch_time + buffer]``
      (KST, 엄격 해석) 기준. 윈도우 종료 이후 검증 시점에 ``last_modified`` 가
      윈도우 안에 있지 않으면 FAIL ("윈도우 내 미적재" / "최종 업데이트 시각
      없음"). ``row_count == 0`` 은 윈도우와 무관하게 FAIL.
      ``batch_time`` / ``buffer_minutes`` 가 None 이면 정책 미설정 폴백으로
      "오늘 미적재" 기준을 사용한다. cond_buffer_load 가 True 인 테이블은
      schema 레벨에서 batch_time 이 NOT NULL 이므로 이 폴백은 정책 미설정
      테스트/외부 호출용이다.
    - `cond_delta_rowcount`: |today - baseline| / baseline
      >= delta_threshold_percent / 100. Baseline 은 daily=어제, monthly=전월.
      Baseline 이 없으면 증감률 비교를 생략하고 사유에 그 사실을 남긴다(FAIL 아님).
    """
    reasons: list[str] = []
    notes: list[str] = []
    actual = now if now is not None else datetime.now(tz=KST)
    today = today_kst(actual)

    if cond_buffer_load:
        if batch_time is not None and buffer_minutes is not None:
            window_start, window_end = buffer_window(
                actual, batch_time, buffer_minutes
            )
            in_buffer = actual.astimezone(KST) < window_end
            if not in_buffer:
                if metadata.last_modified is None:
                    reasons.append("최종 업데이트 시각 없음")
                else:
                    lm_kst = metadata.last_modified.astimezone(KST)
                    if not (window_start <= lm_kst <= window_end):
                        reasons.append("윈도우 내 미적재")
        else:
            # 정책 미설정 폴백: 윈도우 계산이 불가하므로 "오늘 적재 여부" 로 판정.
            if metadata.last_modified is None:
                reasons.append("최종 업데이트 시각 없음")
            elif metadata.last_modified.astimezone(KST).date() != today:
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
        failure_reasons=reasons,
        informational_notes=notes,
        delta_percent_vs_yesterday=(
            None
            if delta_percent is None or delta_percent == float("inf")
            else round(delta_percent, 2)
        ),
    )
