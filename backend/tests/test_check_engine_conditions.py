"""evaluate(): cond_* 토글로 FAIL 억제 + 월간 베이스라인 윈도우 계산."""
from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from dfm_bq_load_alerter.bq.metadata import TableMetadata
from dfm_bq_load_alerter.checks.engine import evaluate
from dfm_bq_load_alerter.checks.runner import _previous_month_window

KST = ZoneInfo("Asia/Seoul")

BATCH_TIME = time(5, 0)
BUFFER_MINUTES = 240  # 버퍼 윈도우 끝 09:00 KST.


def _메타(*, last_modified: datetime | None, row_count: int | None) -> TableMetadata:
    """테스트용 BQ 메타데이터 빌더."""
    return TableMetadata(
        dataset="bw",
        table_name="PZEVENTID",
        last_modified=last_modified,
        row_count=row_count,
        used_count_fallback=False,
    )


def test_cond_buffer_load_가_꺼져있으면_미적재_FAIL이_억제된다() -> None:
    """cond_buffer_load=False → 윈도우 밖 미적재라도 FAIL 사유가 추가되지 않는다."""
    now = datetime(2026, 5, 7, 9, 30, tzinfo=KST)
    md = _메타(last_modified=None, row_count=None)
    result = evaluate(
        md,
        yesterday_row_count=1000,
        delta_threshold_percent=25.0,
        batch_time=BATCH_TIME,
        buffer_minutes=BUFFER_MINUTES,
        now=now,
        cond_buffer_load=False,
    )
    assert "최종 업데이트 시각 없음" not in result.failure_reasons
    assert "row count 0" not in result.failure_reasons


def test_cond_delta_rowcount_가_꺼져있으면_증감률_FAIL이_억제된다() -> None:
    """동일 입력에서 cond_delta_rowcount 토글만 바꿔 증감률 FAIL 발화 여부를 확인."""
    now = datetime(2026, 5, 7, 9, 30, tzinfo=KST)
    today = datetime(2026, 5, 7, 5, 30, tzinfo=KST)
    md = _메타(last_modified=today, row_count=200)  # 1000→200, Δ=80%
    result_on = evaluate(
        md,
        yesterday_row_count=1000,
        delta_threshold_percent=25.0,
        batch_time=BATCH_TIME,
        buffer_minutes=BUFFER_MINUTES,
        now=now,
        cond_delta_rowcount=True,
    )
    result_off = evaluate(
        md,
        yesterday_row_count=1000,
        delta_threshold_percent=25.0,
        batch_time=BATCH_TIME,
        buffer_minutes=BUFFER_MINUTES,
        now=now,
        cond_delta_rowcount=False,
    )
    assert any("증감률 임계치 초과" in r for r in result_on.failure_reasons)
    assert all("증감률 임계치 초과" not in r for r in result_off.failure_reasons)


def test_전월_윈도우는_이전달_1일부터_이번달_1일_직전까지로_계산된다() -> None:
    """2026-05-07 기준 전월 윈도우 = [2026-04-01 00:00, 2026-05-01 00:00) KST."""
    start, end = _previous_month_window(date(2026, 5, 7))
    assert start == datetime(2026, 4, 1, tzinfo=KST)
    assert end == datetime(2026, 5, 1, tzinfo=KST)


def test_전월_윈도우_계산은_1월_경계에서_연도가_바뀐다() -> None:
    """2026-01-15 기준 전월 = [2025-12-01, 2026-01-01) KST."""
    start, end = _previous_month_window(date(2026, 1, 15))
    assert start == datetime(2025, 12, 1, tzinfo=KST)
    assert end == datetime(2026, 1, 1, tzinfo=KST)
