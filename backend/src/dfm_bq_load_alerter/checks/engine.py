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


def load_deadline(
    now: datetime, batch_time: time, buffer_minutes: int
) -> datetime:
    """오늘(KST) 기준 적재 마감 시각: ``batch_time + buffer_minutes``.

    검증 시각이 이 마감보다 이른 동안은 적재가 도착할 여지가 있어 미적재라도
    FAIL 단정 불가, 마감 이후에는 미적재 시 FAIL 로 단정한다.
    """
    today = now.astimezone(KST).date()
    anchor = datetime.combine(today, batch_time, tzinfo=KST)
    return anchor + timedelta(minutes=buffer_minutes)


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
    """단일 (테이블, 메타데이터, 베이스라인) 조합에 대한 상태 판정.

    판정 로직 (rev 4 — SKIP 도입):

    [A] ``cond_buffer_load`` 활성: 적재 여부 / row_count==0 검사
        - 오늘(KST) 일자로 적재 완료 (``last_modified.date() == today``)
            - ``row_count == 0`` → FAIL ("row count 0")
            - 그 외 → 본 분기에서는 FAIL 추가하지 않음 (증감률은 [B] 에서 평가)
        - 오늘 일자로 미적재
            - 현재시각 < ``batch_time + buffer_minutes`` → 마감 이전, 판정 보류
              (SKIP). FAIL 도 OK 도 아님.
            - 현재시각 ≥ ``batch_time + buffer_minutes`` → FAIL
              ("오늘 미적재" 또는 ``last_modified is None`` 일 때
              "최종 업데이트 시각 없음")
        - ``batch_time`` / ``buffer_minutes`` 가 None 이면 정책 미설정 폴백 —
          마감 판단이 불가하므로 "오늘 미적재" 자체로 FAIL.
          cond_buffer_load=True 인 운영 테이블은 스키마상 batch_time 이
          NOT NULL 이므로 이 폴백은 테스트/외부 호출 경로에서만 의미가 있다.

    [B] ``cond_delta_rowcount`` 활성: 증감률 검사
        - cond_buffer_load=True 이면서 오늘 미적재이거나 row_count==0 인
          경우엔 비교 대상이 의미 없으므로 증감률 검사를 건너뛴다.
        - 그 외에는 ``|today - baseline| / baseline`` 을 임계치와 비교한다.
          Baseline 은 daily=어제, monthly=전월. Baseline 이 없으면 비교를
          생략하고 정보성 노트만 남긴다(FAIL 아님).
        - ``baseline == 0`` 이고 ``today > 0`` 이면 0→증가 케이스로
          FAIL 처리.

    상태 우선순위는 FAIL > SKIP > OK 다. cond_buffer_load 가 마감 이전 미적재로
    SKIP 후보를 만들었더라도 [B] 의 증감률 검사가 FAIL 사유를 추가했다면 FAIL 이
    우선한다(현 구현에선 [B] 가 동일 미적재 케이스에서 건너뛰므로 이 충돌은
    실질적으로 발생하지 않지만, 우선순위만 명시한다).
    """
    reasons: list[str] = []
    notes: list[str] = []
    actual = now if now is not None else datetime.now(tz=KST)
    today = today_kst(actual)
    pending_load = False  # 마감 이전 미적재로 SKIP 판정될 수 있는 후보 표식

    loaded_today = (
        metadata.last_modified is not None
        and metadata.last_modified.astimezone(KST).date() == today
    )

    # [A] cond_buffer_load: 적재 여부 + row_count==0
    if cond_buffer_load:
        if loaded_today:
            if metadata.row_count == 0:
                reasons.append("row count 0")
        else:
            if batch_time is not None and buffer_minutes is not None:
                deadline = load_deadline(actual, batch_time, buffer_minutes)
                past_deadline = actual.astimezone(KST) >= deadline
            else:
                # 정책 미설정 폴백 — 마감 계산 불가, "오늘 미적재" 즉시 FAIL.
                past_deadline = True
            if past_deadline:
                if metadata.last_modified is None:
                    reasons.append("최종 업데이트 시각 없음")
                else:
                    reasons.append("오늘 미적재")
            else:
                pending_load = True

    # [B] cond_delta_rowcount: 증감률
    delta_percent: float | None = None
    if cond_delta_rowcount:
        # cond_buffer_load 활성 시: 오늘 적재 + row_count!=0 인 경우에만 비교.
        # cond_buffer_load 비활성 시: 적재 시점 무관하게 row_count 기준으로 비교.
        eligible_for_delta = (not cond_buffer_load) or (
            loaded_today and metadata.row_count not in (None, 0)
        )
        if eligible_for_delta:
            if yesterday_row_count is None:
                notes.append("이전 배치 기록 없음 - 증감률 비교 생략")
            elif yesterday_row_count > 0 and metadata.row_count is not None:
                delta_percent = (
                    (metadata.row_count - yesterday_row_count) / yesterday_row_count
                ) * 100.0
                if abs(delta_percent) >= delta_threshold_percent:
                    reasons.append(
                        f"증감률 임계치 초과: {delta_percent:+.2f}% (|Δ| >= "
                        f"{delta_threshold_percent:.2f}%)"
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

    if reasons:
        status = CheckStatus.fail
    elif pending_load:
        status = CheckStatus.skip
    else:
        status = CheckStatus.ok
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
