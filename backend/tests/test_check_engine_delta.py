"""evaluate(): 전일 대비 증감률 판정 (기본 시나리오).

적재 분기 영향이 결과에 섞이지 않도록, 모든 케이스를 "오늘(KST) 적재 완료 +
row_count > 0" 라는 동일한 적재 상태로 고정하고, row_count 만 바꾼다.
"""
from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from dfm_bq_load_alerter.bq.metadata import TableMetadata
from dfm_bq_load_alerter.checks.engine import evaluate
from dfm_bq_load_alerter.db.models import CheckStatus

KST = ZoneInfo("Asia/Seoul")

BATCH_TIME = time(5, 0)
BUFFER_MINUTES = 30
NOW = datetime(2026, 5, 7, 8, 0, tzinfo=KST)  # 마감(05:30) 이후 검증
LOADED = datetime(2026, 5, 7, 5, 0, tzinfo=KST)  # 오늘(KST) 적재 완료


def _메타(*, row_count: int) -> TableMetadata:
    """테스트용 BQ 메타데이터 빌더 (오늘 적재 완료 상태로 고정)."""
    return TableMetadata(
        dataset="bw",
        table_name="PZEVENTID",
        last_modified=LOADED,
        row_count=row_count,
        used_count_fallback=False,
    )


def test_증감률이_임계치_이내면_OK이다() -> None:
    """|1000 → 1050| / 1000 = 5% < 25% → OK."""
    result = evaluate(
        _메타(row_count=1050),
        yesterday_row_count=1000,
        delta_threshold_percent=25.0,
        batch_time=BATCH_TIME,
        buffer_minutes=BUFFER_MINUTES,
        now=NOW,
    )
    assert result.status == CheckStatus.ok
    assert result.failure_reasons == []
    assert result.delta_percent_vs_yesterday == 5.0


def test_증감률이_임계치_이상이면_FAIL이다() -> None:
    """|1000 → 400| / 1000 = 60% ≥ 25% → FAIL."""
    result = evaluate(
        _메타(row_count=400),
        yesterday_row_count=1000,
        delta_threshold_percent=25.0,
        batch_time=BATCH_TIME,
        buffer_minutes=BUFFER_MINUTES,
        now=NOW,
    )
    assert result.status == CheckStatus.fail
    assert any(r.startswith("증감률 임계치 초과") for r in result.failure_reasons)
    assert result.delta_percent_vs_yesterday == 60.0


def test_베이스라인이_없으면_증감률_비교를_생략한다() -> None:
    """yesterday_row_count=None → FAIL 사유 없음 + 정보성 노트만 기록."""
    result = evaluate(
        _메타(row_count=1000),
        yesterday_row_count=None,
        delta_threshold_percent=25.0,
        batch_time=BATCH_TIME,
        buffer_minutes=BUFFER_MINUTES,
        now=NOW,
    )
    assert result.status == CheckStatus.ok
    assert result.failure_reasons == []
    assert "이전 배치 기록 없음 - 증감률 비교 생략" in result.informational_notes
    assert result.delta_percent_vs_yesterday is None
