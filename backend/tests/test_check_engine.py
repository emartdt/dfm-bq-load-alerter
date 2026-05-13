"""evaluate(): 기본 OK/FAIL 판정 + today_kst / is_skip_for_monthly 동작."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from freezegun import freeze_time

from dfm_bq_load_alerter.bq.metadata import TableMetadata
from dfm_bq_load_alerter.checks.engine import (
    evaluate,
    is_skip_for_monthly,
    today_kst,
)
from dfm_bq_load_alerter.db.models import CheckStatus, Frequency

KST = ZoneInfo("Asia/Seoul")


def _메타(*, last_modified: datetime | None, row_count: int | None) -> TableMetadata:
    """테스트용 BQ 메타데이터 빌더."""
    return TableMetadata(
        dataset="bw",
        table_name="PZEVENTID",
        last_modified=last_modified,
        row_count=row_count,
        used_count_fallback=False,
    )


def test_today_kst_는_서울_시간대_기준으로_날짜를_돌려준다() -> None:
    """UTC 14:59 = KST 23:59 (같은 날), UTC 15:00 = KST 00:00 (다음 날)."""
    with freeze_time(datetime(2026, 5, 6, 14, 59, tzinfo=ZoneInfo("UTC"))):
        assert today_kst() == date(2026, 5, 6)
    with freeze_time(datetime(2026, 5, 6, 15, 0, tzinfo=ZoneInfo("UTC"))):
        assert today_kst() == date(2026, 5, 7)


def test_오늘_적재되었고_증감률이_임계치_이내면_OK() -> None:
    """last_modified 가 오늘이고 |Δ%| < threshold → 정상 판정."""
    with freeze_time(datetime(2026, 5, 6, 8, 0, tzinfo=KST)):
        result = evaluate(
            _메타(
                last_modified=datetime(2026, 5, 6, 5, 30, tzinfo=KST),
                row_count=1_000_000,
            ),
            yesterday_row_count=950_000,
            delta_threshold_percent=25.0,
        )
    assert result.status == CheckStatus.ok
    assert result.failure_reasons == []
    assert result.delta_percent_vs_yesterday is not None
    assert 5.2 < result.delta_percent_vs_yesterday < 5.3


def test_오늘_미적재면_FAIL_사유에_오늘_미적재가_포함된다() -> None:
    """last_modified 가 어제 이전 → '오늘 미적재' FAIL."""
    with freeze_time(datetime(2026, 5, 6, 8, 0, tzinfo=KST)):
        result = evaluate(
            _메타(
                last_modified=datetime(2026, 5, 5, 23, 0, tzinfo=KST),
                row_count=100,
            ),
            yesterday_row_count=100,
            delta_threshold_percent=25.0,
        )
    assert result.status == CheckStatus.fail
    assert "오늘 미적재" in result.failure_reasons


def test_row_count_가_0이면_FAIL이다() -> None:
    """row_count==0 은 버퍼/적재 여부와 무관하게 FAIL."""
    with freeze_time(datetime(2026, 5, 6, 8, 0, tzinfo=KST)):
        result = evaluate(
            _메타(
                last_modified=datetime(2026, 5, 6, 5, 0, tzinfo=KST),
                row_count=0,
            ),
            yesterday_row_count=100,
            delta_threshold_percent=25.0,
        )
    assert result.status == CheckStatus.fail
    assert "row count 0" in result.failure_reasons


def test_증감률이_임계치_이상이면_FAIL이다() -> None:
    """|1000 → 400| / 1000 = 60% ≥ 25% → 증감률 임계치 초과 FAIL."""
    with freeze_time(datetime(2026, 5, 6, 8, 0, tzinfo=KST)):
        result = evaluate(
            _메타(
                last_modified=datetime(2026, 5, 6, 5, 0, tzinfo=KST),
                row_count=400,
            ),
            yesterday_row_count=1000,
            delta_threshold_percent=25.0,
        )
    assert result.status == CheckStatus.fail
    assert any(r.startswith("증감률 임계치 초과") for r in result.failure_reasons)
    assert result.delta_percent_vs_yesterday == 60.0


def test_베이스라인이_없고_다른_문제가_없으면_OK이며_정보성_노트가_남는다() -> None:
    """전일 베이스라인이 없으면 증감률 비교를 건너뛰고 OK + 정보성 노트.

    노트는 FAIL 사유가 아니므로 ``informational_notes`` 에 기록되어
    알람 템플릿에서도 빨간 ⚠ 가 아닌 파란 ⓘ 로 구분 렌더된다.
    """
    with freeze_time(datetime(2026, 5, 6, 8, 0, tzinfo=KST)):
        result = evaluate(
            _메타(
                last_modified=datetime(2026, 5, 6, 5, 0, tzinfo=KST),
                row_count=100,
            ),
            yesterday_row_count=None,
            delta_threshold_percent=25.0,
        )
    assert result.status == CheckStatus.ok
    assert result.failure_reasons == []
    assert result.informational_notes == ["이전 배치 기록 없음 - 증감률 비교 생략"]
    assert result.delta_percent_vs_yesterday is None


def test_베이스라인이_없어도_다른_FAIL_사유가_있으면_FAIL이고_정보성_노트는_별도로_기록된다() -> None:
    """베이스라인 없음은 정보성 노트로, 미적재는 실패 사유로 분리 기록된다."""
    with freeze_time(datetime(2026, 5, 6, 8, 0, tzinfo=KST)):
        result = evaluate(
            _메타(
                last_modified=datetime(2026, 5, 5, 5, 0, tzinfo=KST),
                row_count=100,
            ),
            yesterday_row_count=None,
            delta_threshold_percent=25.0,
        )
    assert result.status == CheckStatus.fail
    assert "오늘 미적재" in result.failure_reasons
    assert "이전 배치 기록 없음 - 증감률 비교 생략" not in result.failure_reasons
    assert "이전 배치 기록 없음 - 증감률 비교 생략" in result.informational_notes


def test_월간_테이블은_배치일이_아닌_날짜에는_점검을_스킵한다() -> None:
    """daily 는 batch_day_of_month 와 무관, monthly 는 당일에만 점검."""
    today = date(2026, 5, 6)
    assert is_skip_for_monthly(Frequency.monthly, batch_day_of_month=1, today=today)
    assert not is_skip_for_monthly(
        Frequency.monthly, batch_day_of_month=6, today=today
    )
    # daily 는 batch_day_of_month 를 무시한다.
    assert not is_skip_for_monthly(Frequency.daily, batch_day_of_month=1, today=today)
