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


def test_윈도우_안_적재이고_row_count_0이면_버퍼_상태와_무관하게_FAIL이다() -> None:
    """윈도우 안 적재(05:30)에서 비어 있으면 검증 시각이 in_buffer 든 아니든 FAIL."""
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


def test_윈도우_밖_적재이면_row_count_0_사유는_발화하지_않는다() -> None:
    """윈도우 밖 적재 케이스는 '윈도우 내 미적재' 가 표현하므로 row_count 검사 생략."""
    now = datetime(2026, 5, 7, 9, 30, tzinfo=KST)  # 윈도우 종료 09:00 이후
    early = datetime(2026, 5, 7, 0, 30, tzinfo=KST)  # 윈도우 시작(01:00) 이전
    md = _메타(last_modified=early, row_count=0)
    result = evaluate(
        md,
        yesterday_row_count=1000,
        delta_threshold_percent=25.0,
        batch_time=BATCH_TIME,
        buffer_minutes=BUFFER_MINUTES,
        now=now,
    )
    assert result.status == CheckStatus.fail
    assert "윈도우 내 미적재" in result.failure_reasons
    assert "row count 0" not in result.failure_reasons


def test_미적재_상태에서는_row_count_0_사유는_발화하지_않는다() -> None:
    """last_modified 가 None 이면 row_count 검사 자체가 적용되지 않는다."""
    now = datetime(2026, 5, 7, 9, 30, tzinfo=KST)
    md = _메타(last_modified=None, row_count=0)
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
    assert "row count 0" not in result.failure_reasons


# 엄격 해석 A: 윈도우 = [batch - buffer, batch + buffer]. 적재 시각이 윈도우
# 안에 있어야 정상. 윈도우 밖(이전/이후)에 적재되어도 FAIL.
TIGHT_BATCH = time(5, 0)
TIGHT_BUFFER = 30  # 윈도우 = [04:30, 05:30] KST.


def test_적재가_윈도우_시작_전이면_FAIL이며_사유는_윈도우_내_미적재이다() -> None:
    """batch=05:00, buffer=30 → 윈도우[04:30, 05:30]. 03:00 적재 → 윈도우 밖."""
    now = datetime(2026, 5, 7, 6, 0, tzinfo=KST)
    loaded = datetime(2026, 5, 7, 3, 0, tzinfo=KST)
    md = _메타(last_modified=loaded, row_count=1000)
    result = evaluate(
        md,
        yesterday_row_count=1000,
        delta_threshold_percent=25.0,
        batch_time=TIGHT_BATCH,
        buffer_minutes=TIGHT_BUFFER,
        now=now,
    )
    assert result.status == CheckStatus.fail
    assert "윈도우 내 미적재" in result.failure_reasons
    # 강조: 같은 입력에서 구(舊) 사유는 발화하지 않는다.
    assert "오늘 미적재" not in result.failure_reasons


def test_적재가_윈도우_종료_이후면_FAIL이다() -> None:
    """윈도우 종료(05:30) 이후 적재(05:45)는 엄격 해석으로 FAIL."""
    now = datetime(2026, 5, 7, 6, 0, tzinfo=KST)
    loaded = datetime(2026, 5, 7, 5, 45, tzinfo=KST)
    md = _메타(last_modified=loaded, row_count=1000)
    result = evaluate(
        md,
        yesterday_row_count=1000,
        delta_threshold_percent=25.0,
        batch_time=TIGHT_BATCH,
        buffer_minutes=TIGHT_BUFFER,
        now=now,
    )
    assert result.status == CheckStatus.fail
    assert "윈도우 내 미적재" in result.failure_reasons


def test_적재가_윈도우_안이면_OK이다() -> None:
    """윈도우[04:30, 05:30] 안 적재(05:15) → 정상."""
    now = datetime(2026, 5, 7, 6, 0, tzinfo=KST)
    loaded = datetime(2026, 5, 7, 5, 15, tzinfo=KST)
    md = _메타(last_modified=loaded, row_count=1000)
    result = evaluate(
        md,
        yesterday_row_count=1000,
        delta_threshold_percent=25.0,
        batch_time=TIGHT_BATCH,
        buffer_minutes=TIGHT_BUFFER,
        now=now,
    )
    assert result.status == CheckStatus.ok
    assert "윈도우 내 미적재" not in result.failure_reasons


def test_윈도우_경계값은_포함이다() -> None:
    """경계(04:30, 05:30) 정확히 적재된 경우는 윈도우 안으로 인정."""
    now = datetime(2026, 5, 7, 6, 0, tzinfo=KST)
    md_start = _메타(
        last_modified=datetime(2026, 5, 7, 4, 30, tzinfo=KST), row_count=1000
    )
    md_end = _메타(
        last_modified=datetime(2026, 5, 7, 5, 30, tzinfo=KST), row_count=1000
    )
    for md in (md_start, md_end):
        result = evaluate(
            md,
            yesterday_row_count=1000,
            delta_threshold_percent=25.0,
            batch_time=TIGHT_BATCH,
            buffer_minutes=TIGHT_BUFFER,
            now=now,
        )
        assert result.status == CheckStatus.ok, (
            f"경계 적재가 OK 여야 함: last_modified={md.last_modified}"
        )


def test_윈도우_안에서는_과거_시각_적재여도_FAIL이_아니다() -> None:
    """윈도우 종료(05:30) 전이라면 적재가 어디든 'still in flight' 로 본다."""
    now = datetime(2026, 5, 7, 5, 0, tzinfo=KST)
    loaded = datetime(2026, 5, 7, 3, 0, tzinfo=KST)
    md = _메타(last_modified=loaded, row_count=1000)
    result = evaluate(
        md,
        yesterday_row_count=1000,
        delta_threshold_percent=25.0,
        batch_time=TIGHT_BATCH,
        buffer_minutes=TIGHT_BUFFER,
        now=now,
    )
    assert "윈도우 내 미적재" not in result.failure_reasons
