"""evaluate(): "오늘 적재 여부" 기반 적재 판정 (기본 시나리오).

판정 축:
- 오늘(KST) 적재 완료 → row_count==0 만 FAIL 사유.
- 오늘 미적재 → 검증 시각이 ``batch_time + buffer_minutes`` 마감 이전이면
  대기 중(FAIL 아님), 마감 이후이면 FAIL.
"""
from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from dfm_bq_load_alerter.bq.metadata import TableMetadata
from dfm_bq_load_alerter.checks.engine import evaluate
from dfm_bq_load_alerter.db.models import CheckStatus

KST = ZoneInfo("Asia/Seoul")

# batch_time=05:00 + buffer=30 → 적재 마감 05:30 KST.
BATCH_TIME = time(5, 0)
BUFFER_MINUTES = 30


def _메타(*, last_modified: datetime | None, row_count: int | None) -> TableMetadata:
    """테스트용 BQ 메타데이터 빌더."""
    return TableMetadata(
        dataset="bw",
        table_name="PZEVENTID",
        last_modified=last_modified,
        row_count=row_count,
        used_count_fallback=False,
    )


def test_오늘_적재되었으면_OK이다() -> None:
    """오늘(05:00) 적재 + row_count>0, 검증 08:00 → OK."""
    now = datetime(2026, 5, 7, 8, 0, tzinfo=KST)
    loaded = datetime(2026, 5, 7, 5, 0, tzinfo=KST)
    result = evaluate(
        _메타(last_modified=loaded, row_count=1000),
        yesterday_row_count=1000,
        delta_threshold_percent=25.0,
        batch_time=BATCH_TIME,
        buffer_minutes=BUFFER_MINUTES,
        now=now,
    )
    assert result.status == CheckStatus.ok
    assert result.failure_reasons == []


def test_오늘_적재되었지만_마감_이전_적재라도_OK이다() -> None:
    """오늘 적재만 되어 있으면 마감(05:30) 이전이든 이후이든 OK 로 본다.

    구버전은 윈도우 [04:30, 05:30] 밖 적재(예: 04:00)를 FAIL 처리했으나,
    신규 로직은 "오늘 적재" 만 충족하면 시각에 무관하게 OK 로 평가한다.
    """
    now = datetime(2026, 5, 7, 8, 0, tzinfo=KST)
    loaded = datetime(2026, 5, 7, 4, 0, tzinfo=KST)  # 마감 이전 적재
    result = evaluate(
        _메타(last_modified=loaded, row_count=1000),
        yesterday_row_count=1000,
        delta_threshold_percent=25.0,
        batch_time=BATCH_TIME,
        buffer_minutes=BUFFER_MINUTES,
        now=now,
    )
    assert result.status == CheckStatus.ok
    assert result.failure_reasons == []


def test_마감_이후_미적재면_FAIL이다() -> None:
    """검증 시각이 마감(05:30) 이후이고 last_modified=None → '최종 업데이트 시각 없음' FAIL."""
    now = datetime(2026, 5, 7, 8, 0, tzinfo=KST)
    result = evaluate(
        _메타(last_modified=None, row_count=None),
        yesterday_row_count=1000,
        delta_threshold_percent=25.0,
        batch_time=BATCH_TIME,
        buffer_minutes=BUFFER_MINUTES,
        now=now,
    )
    assert result.status == CheckStatus.fail
    assert "최종 업데이트 시각 없음" in result.failure_reasons


def test_마감_이후_어제까지만_적재되어_있으면_FAIL이다() -> None:
    """오늘 미적재이고 마감(05:30) 이후 → '오늘 미적재' FAIL."""
    now = datetime(2026, 5, 7, 8, 0, tzinfo=KST)
    loaded_yesterday = datetime(2026, 5, 6, 5, 0, tzinfo=KST)
    result = evaluate(
        _메타(last_modified=loaded_yesterday, row_count=1000),
        yesterday_row_count=1000,
        delta_threshold_percent=25.0,
        batch_time=BATCH_TIME,
        buffer_minutes=BUFFER_MINUTES,
        now=now,
    )
    assert result.status == CheckStatus.fail
    assert "오늘 미적재" in result.failure_reasons


def test_마감_이전에는_미적재여도_FAIL이_아니다() -> None:
    """검증 시각이 마감(05:30) 이전이면 적재 대기 중 — FAIL 단정 불가."""
    now = datetime(2026, 5, 7, 5, 0, tzinfo=KST)
    result = evaluate(
        _메타(last_modified=None, row_count=None),
        yesterday_row_count=1000,
        delta_threshold_percent=25.0,
        batch_time=BATCH_TIME,
        buffer_minutes=BUFFER_MINUTES,
        now=now,
    )
    assert result.status == CheckStatus.ok
    assert result.failure_reasons == []


def test_오늘_적재되었지만_row_count가_0이면_FAIL이다() -> None:
    """오늘 적재 + row_count==0 → 'row count 0' FAIL."""
    now = datetime(2026, 5, 7, 8, 0, tzinfo=KST)
    loaded = datetime(2026, 5, 7, 5, 0, tzinfo=KST)
    result = evaluate(
        _메타(last_modified=loaded, row_count=0),
        yesterday_row_count=1000,
        delta_threshold_percent=25.0,
        batch_time=BATCH_TIME,
        buffer_minutes=BUFFER_MINUTES,
        now=now,
    )
    assert result.status == CheckStatus.fail
    assert "row count 0" in result.failure_reasons


def test_오늘_적재_row_count_0_이면_증감률_FAIL_사유는_중복되지_않는다() -> None:
    """row_count==0 으로 FAIL 시 증감률 임계치 사유는 추가하지 않는다.

    yesterday=1000, today=0 이면 증감률 100% 이지만, 신규 로직은 row_count==0
    분기에서 증감률 검사를 건너뛰어 사유 중복을 막는다.
    """
    now = datetime(2026, 5, 7, 8, 0, tzinfo=KST)
    loaded = datetime(2026, 5, 7, 5, 0, tzinfo=KST)
    result = evaluate(
        _메타(last_modified=loaded, row_count=0),
        yesterday_row_count=1000,
        delta_threshold_percent=25.0,
        batch_time=BATCH_TIME,
        buffer_minutes=BUFFER_MINUTES,
        now=now,
    )
    assert "row count 0" in result.failure_reasons
    assert not any(
        r.startswith("증감률 임계치 초과") for r in result.failure_reasons
    )
