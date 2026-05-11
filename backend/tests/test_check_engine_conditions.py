"""evaluate(): condition OR toggles + monthly baseline window."""
from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from dfm_bq_load_alerter.bq.metadata import TableMetadata
from dfm_bq_load_alerter.checks.engine import evaluate
from dfm_bq_load_alerter.checks.runner import _previous_month_window

KST = ZoneInfo("Asia/Seoul")

BATCH_TIME = time(5, 0)
BUFFER_MINUTES = 240  # 윈도우 끝 09:00


def _md(*, last_modified: datetime | None, row_count: int | None) -> TableMetadata:
    return TableMetadata(
        dataset="bw",
        table_name="PZEVENTID",
        last_modified=last_modified,
        row_count=row_count,
        used_count_fallback=False,
    )


def test_cond_buffer_load_off_suppresses_buffer_failures() -> None:
    """When cond_buffer_load=False, post-window missing-load is no longer FAIL."""
    now = datetime(2026, 5, 7, 9, 30, tzinfo=KST)
    md = _md(last_modified=None, row_count=None)
    result = evaluate(
        md,
        yesterday_row_count=1000,
        delta_threshold_percent=25.0,
        batch_time=BATCH_TIME,
        buffer_minutes=BUFFER_MINUTES,
        now=now,
        cond_buffer_load=False,
    )
    assert "missing_last_modified" not in result.failure_reasons
    assert "row_count_zero" not in result.failure_reasons


def test_cond_delta_off_suppresses_delta_failures() -> None:
    """80% delta: with cond_delta_rowcount=False the FAIL is suppressed."""
    now = datetime(2026, 5, 7, 9, 30, tzinfo=KST)
    today = datetime(2026, 5, 7, 5, 30, tzinfo=KST)
    md = _md(last_modified=today, row_count=200)
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
    assert any("delta_exceeded" in r for r in result_on.failure_reasons)
    assert all("delta_exceeded" not in r for r in result_off.failure_reasons)


def test_previous_month_window_calculates_first_to_first_of_month() -> None:
    start, end = _previous_month_window(date(2026, 5, 7))
    assert start == datetime(2026, 4, 1, tzinfo=KST)
    assert end == datetime(2026, 5, 1, tzinfo=KST)


def test_previous_month_window_handles_january() -> None:
    start, end = _previous_month_window(date(2026, 1, 15))
    assert start == datetime(2025, 12, 1, tzinfo=KST)
    assert end == datetime(2026, 1, 1, tzinfo=KST)
