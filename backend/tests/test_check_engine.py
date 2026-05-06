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


def _meta(*, last_modified: datetime | None, row_count: int | None) -> TableMetadata:
    return TableMetadata(
        dataset="bw",
        table_name="PZEVENTID",
        last_modified=last_modified,
        row_count=row_count,
        used_count_fallback=False,
    )


def test_today_kst_uses_seoul_zone() -> None:
    # UTC 14:59 = KST 23:59 (same day) ; UTC 15:00 = KST 00:00 (next day)
    with freeze_time(datetime(2026, 5, 6, 14, 59, tzinfo=ZoneInfo("UTC"))):
        assert today_kst() == date(2026, 5, 6)
    with freeze_time(datetime(2026, 5, 6, 15, 0, tzinfo=ZoneInfo("UTC"))):
        assert today_kst() == date(2026, 5, 7)


def test_status_ok_when_modified_today_and_within_threshold() -> None:
    with freeze_time(datetime(2026, 5, 6, 8, 0, tzinfo=KST)):
        result = evaluate(
            _meta(
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


def test_fail_when_not_updated_today() -> None:
    with freeze_time(datetime(2026, 5, 6, 8, 0, tzinfo=KST)):
        result = evaluate(
            _meta(
                last_modified=datetime(2026, 5, 5, 23, 0, tzinfo=KST),
                row_count=100,
            ),
            yesterday_row_count=100,
            delta_threshold_percent=25.0,
        )
    assert result.status == CheckStatus.fail
    assert "not_updated_today_kst" in result.failure_reasons


def test_fail_when_row_count_zero() -> None:
    with freeze_time(datetime(2026, 5, 6, 8, 0, tzinfo=KST)):
        result = evaluate(
            _meta(
                last_modified=datetime(2026, 5, 6, 5, 0, tzinfo=KST),
                row_count=0,
            ),
            yesterday_row_count=100,
            delta_threshold_percent=25.0,
        )
    assert result.status == CheckStatus.fail
    assert "row_count_zero" in result.failure_reasons


def test_fail_when_delta_exceeds_threshold() -> None:
    with freeze_time(datetime(2026, 5, 6, 8, 0, tzinfo=KST)):
        result = evaluate(
            _meta(
                last_modified=datetime(2026, 5, 6, 5, 0, tzinfo=KST),
                row_count=400,
            ),
            yesterday_row_count=1000,
            delta_threshold_percent=25.0,
        )
    assert result.status == CheckStatus.fail
    assert any(r.startswith("delta_exceeded") for r in result.failure_reasons)
    assert result.delta_percent_vs_yesterday == 60.0


def test_insufficient_history_when_no_yesterday_and_otherwise_ok() -> None:
    with freeze_time(datetime(2026, 5, 6, 8, 0, tzinfo=KST)):
        result = evaluate(
            _meta(
                last_modified=datetime(2026, 5, 6, 5, 0, tzinfo=KST),
                row_count=100,
            ),
            yesterday_row_count=None,
            delta_threshold_percent=25.0,
        )
    assert result.status == CheckStatus.insufficient_history
    assert result.failure_reasons == []


def test_fail_overrides_insufficient_history_when_other_reasons_exist() -> None:
    with freeze_time(datetime(2026, 5, 6, 8, 0, tzinfo=KST)):
        result = evaluate(
            _meta(
                last_modified=datetime(2026, 5, 5, 5, 0, tzinfo=KST),
                row_count=100,
            ),
            yesterday_row_count=None,
            delta_threshold_percent=25.0,
        )
    assert result.status == CheckStatus.fail
    assert "not_updated_today_kst" in result.failure_reasons


def test_monthly_skip_outside_batch_day() -> None:
    today = date(2026, 5, 6)
    assert is_skip_for_monthly(Frequency.monthly, batch_day_of_month=1, today=today)
    assert not is_skip_for_monthly(
        Frequency.monthly, batch_day_of_month=6, today=today
    )
    # daily 는 batch_day_of_month 무시
    assert not is_skip_for_monthly(Frequency.daily, batch_day_of_month=1, today=today)
