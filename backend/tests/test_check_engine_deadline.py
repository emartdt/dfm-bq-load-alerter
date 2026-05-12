"""evaluate(): batch_time + buffer_minutes 윈도우 안/밖에서의 FAIL 억제 동작."""
from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from dfm_bq_load_alerter.bq.metadata import TableMetadata
from dfm_bq_load_alerter.checks.engine import evaluate
from dfm_bq_load_alerter.db.models import CheckStatus

KST = ZoneInfo("Asia/Seoul")

# batch_time=05:00 + buffer=240분 → 버퍼 윈도우 끝 09:00 KST.
BATCH_TIME = time(5, 0)
BUFFER_MINUTES = 240


def _메타(*, last_modified: datetime | None, row_count: int | None) -> TableMetadata:
    """테스트용 BQ 메타데이터 빌더."""
    return TableMetadata(
        dataset="bw",
        table_name="PZEVENTID",
        last_modified=last_modified,
        row_count=row_count,
        used_count_fallback=False,
    )


def test_버퍼_윈도우_안에서는_미적재여도_FAIL이_아니다() -> None:
    """06:00 KST (윈도우 끝 09:00) 시점 미적재는 아직 정상 범주."""
    now = datetime(2026, 5, 7, 6, 0, tzinfo=KST)
    md = _메타(last_modified=None, row_count=None)
    result = evaluate(
        md,
        yesterday_row_count=1000,
        delta_threshold_percent=25.0,
        batch_time=BATCH_TIME,
        buffer_minutes=BUFFER_MINUTES,
        now=now,
    )
    assert result.status == CheckStatus.ok
    assert "최종 업데이트 시각 없음" not in result.failure_reasons


def test_버퍼_윈도우_밖에서_미적재면_FAIL이다() -> None:
    """09:30 KST (윈도우 끝 09:00) 시점 미적재는 FAIL."""
    now = datetime(2026, 5, 7, 9, 30, tzinfo=KST)
    md = _메타(last_modified=None, row_count=None)
    result = evaluate(
        md,
        yesterday_row_count=1000,
        delta_threshold_percent=25.0,
        batch_time=BATCH_TIME,
        buffer_minutes=BUFFER_MINUTES,
        now=now,
    )
    assert result.status == CheckStatus.fail
    assert "최종 업데이트 시각 없음" in result.failure_reasons


def test_버퍼_윈도우_안에서는_last_modified가_어제여도_오늘_미적재_사유로_보지_않는다() -> None:
    """last_modified 가 어제 23:30 이지만 윈도우 내라면 적재 대기 상태."""
    now = datetime(2026, 5, 7, 7, 0, tzinfo=KST)
    yesterday = datetime(2026, 5, 6, 23, 30, tzinfo=KST)
    md = _메타(last_modified=yesterday, row_count=900)
    result = evaluate(
        md,
        yesterday_row_count=1000,
        delta_threshold_percent=25.0,
        batch_time=BATCH_TIME,
        buffer_minutes=BUFFER_MINUTES,
        now=now,
    )
    assert "오늘 미적재" not in result.failure_reasons


def test_row_count_가_0이면_버퍼_안이라도_FAIL이다() -> None:
    """적재되었으나 비어 있는 경우는 버퍼 상태와 무관하게 FAIL."""
    now = datetime(2026, 5, 7, 6, 0, tzinfo=KST)
    today = datetime(2026, 5, 7, 5, 30, tzinfo=KST)
    md = _메타(last_modified=today, row_count=0)
    result = evaluate(
        md,
        yesterday_row_count=1000,
        delta_threshold_percent=25.0,
        batch_time=BATCH_TIME,
        buffer_minutes=BUFFER_MINUTES,
        now=now,
    )
    assert result.status == CheckStatus.fail
    assert "row count 0" in result.failure_reasons
