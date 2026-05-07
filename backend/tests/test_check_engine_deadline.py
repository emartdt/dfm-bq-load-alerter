"""evaluate(): deadline buffer suppression (PR-C)."""
from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from dfm_bq_load_alerter.bq.metadata import TableMetadata
from dfm_bq_load_alerter.checks.engine import evaluate
from dfm_bq_load_alerter.db.models import CheckStatus

KST = ZoneInfo("Asia/Seoul")


def _md(*, last_modified: datetime | None, row_count: int | None) -> TableMetadata:
    return TableMetadata(
        dataset="bw",
        table_name="PZEVENTID",
        last_modified=last_modified,
        row_count=row_count,
        used_count_fallback=False,
    )


def test_pre_deadline_with_no_load_does_not_fail() -> None:
    """At 06:00 KST with deadline 09:00, missing load is still in buffer."""
    now = datetime(2026, 5, 7, 6, 0, tzinfo=KST)
    md = _md(last_modified=None, row_count=None)
    result = evaluate(
        md,
        yesterday_row_count=1000,
        delta_threshold_percent=25.0,
        deadline_time=time(9, 0),
        now=now,
    )
    assert result.status == CheckStatus.ok
    assert "missing_last_modified" not in result.failure_reasons


def test_post_deadline_with_no_load_fails() -> None:
    """At 09:30 KST with deadline 09:00, missing load is now a FAIL."""
    now = datetime(2026, 5, 7, 9, 30, tzinfo=KST)
    md = _md(last_modified=None, row_count=None)
    result = evaluate(
        md,
        yesterday_row_count=1000,
        delta_threshold_percent=25.0,
        deadline_time=time(9, 0),
        now=now,
    )
    assert result.status == CheckStatus.fail
    assert "missing_last_modified" in result.failure_reasons


def test_pre_deadline_with_yesterday_last_modified_is_not_a_fail() -> None:
    """A table whose last_modified is yesterday's date but we're still in
    buffer must NOT raise not_updated_today_kst."""
    now = datetime(2026, 5, 7, 7, 0, tzinfo=KST)
    yesterday = datetime(2026, 5, 6, 23, 30, tzinfo=KST)
    md = _md(last_modified=yesterday, row_count=900)
    result = evaluate(
        md,
        yesterday_row_count=1000,
        delta_threshold_percent=25.0,
        deadline_time=time(9, 0),
        now=now,
    )
    assert "not_updated_today_kst" not in result.failure_reasons


def test_row_count_zero_is_a_fail_even_in_buffer() -> None:
    """Row count == 0 is a fail regardless of deadline (loaded but empty)."""
    now = datetime(2026, 5, 7, 6, 0, tzinfo=KST)
    today = datetime(2026, 5, 7, 5, 30, tzinfo=KST)
    md = _md(last_modified=today, row_count=0)
    result = evaluate(
        md,
        yesterday_row_count=1000,
        delta_threshold_percent=25.0,
        deadline_time=time(9, 0),
        now=now,
    )
    assert result.status == CheckStatus.fail
    assert "row_count_zero" in result.failure_reasons
