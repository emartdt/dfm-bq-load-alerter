"""evaluate(): 버퍼 윈도우 기반 적재 판정 (기본 시나리오)."""
from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from dfm_bq_load_alerter.bq.metadata import TableMetadata
from dfm_bq_load_alerter.checks.engine import evaluate
from dfm_bq_load_alerter.db.models import CheckStatus

KST = ZoneInfo("Asia/Seoul")

# batch_time=05:00 + buffer=30 → 윈도우 [04:30, 05:30] KST.
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


def test_윈도우_안에_적재되었으면_OK이다() -> None:
    """윈도우[04:30, 05:30] 안 적재(05:00), 검증은 윈도우 종료 후(08:00) → OK."""
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


def test_윈도우_종료_후_미적재면_FAIL이다() -> None:
    """검증 시각이 윈도우 종료(05:30) 이후이고 last_modified 가 None → FAIL."""
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


def test_윈도우_종료_전에는_미적재여도_FAIL이_아니다() -> None:
    """검증 시각이 윈도우 안(05:00)이면 아직 대기 중 — FAIL 단정 불가."""
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
    assert "최종 업데이트 시각 없음" not in result.failure_reasons


def test_윈도우_안에_적재되었지만_row_count가_0이면_FAIL이다() -> None:
    """윈도우 안 적재 + row_count==0 → 'row count 0' FAIL."""
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
