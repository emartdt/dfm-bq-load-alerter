"""evaluate(): condition OR toggles + inflow drift + monthly baseline (PR-E)."""
from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from dfm_bq_load_alerter.bq.metadata import TableMetadata
from dfm_bq_load_alerter.checks.engine import _inflow_drift_minutes, evaluate
from dfm_bq_load_alerter.checks.runner import _previous_month_window
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


def test_cond_buffer_load_off_suppresses_buffer_failures() -> None:
    """When cond_buffer_load=False, post-deadline missing-load is no longer FAIL."""
    now = datetime(2026, 5, 7, 9, 30, tzinfo=KST)
    md = _md(last_modified=None, row_count=None)
    result = evaluate(
        md,
        yesterday_row_count=1000,
        delta_threshold_percent=25.0,
        deadline_time=time(9, 0),
        now=now,
        cond_buffer_load=False,
    )
    assert "missing_last_modified" not in result.failure_reasons
    assert "row_count_zero" not in result.failure_reasons


def test_cond_delta_off_suppresses_delta_failures() -> None:
    """100% delta: with cond_delta_rowcount=False the FAIL is suppressed."""
    now = datetime(2026, 5, 7, 9, 30, tzinfo=KST)
    today = datetime(2026, 5, 7, 5, 30, tzinfo=KST)
    md = _md(last_modified=today, row_count=200)
    result_on = evaluate(
        md,
        yesterday_row_count=1000,
        delta_threshold_percent=25.0,
        deadline_time=time(9, 0),
        now=now,
        cond_delta_rowcount=True,
    )
    result_off = evaluate(
        md,
        yesterday_row_count=1000,
        delta_threshold_percent=25.0,
        deadline_time=time(9, 0),
        now=now,
        cond_delta_rowcount=False,
    )
    assert any("delta_exceeded" in r for r in result_on.failure_reasons)
    assert all("delta_exceeded" not in r for r in result_off.failure_reasons)


def test_cond_inflow_time_drift_fails_on_late_load() -> None:
    """어제 03:30, 오늘 05:00 → 90분 drift > 60분 임계치 → FAIL."""
    yesterday_lm = datetime(2026, 5, 6, 3, 30, tzinfo=KST)
    today_lm = datetime(2026, 5, 7, 5, 0, tzinfo=KST)
    md = _md(last_modified=today_lm, row_count=1000)
    result = evaluate(
        md,
        yesterday_row_count=1000,
        delta_threshold_percent=25.0,
        deadline_time=time(9, 0),
        now=datetime(2026, 5, 7, 6, 0, tzinfo=KST),
        cond_inflow_time_drift=True,
        inflow_drift_threshold_minutes=60,
        baseline_last_modified=yesterday_lm,
    )
    assert any("inflow_drift" in r for r in result.failure_reasons)
    assert result.status == CheckStatus.fail


def test_cond_inflow_time_drift_within_threshold_does_not_fail() -> None:
    yesterday_lm = datetime(2026, 5, 6, 3, 30, tzinfo=KST)
    today_lm = datetime(2026, 5, 7, 3, 50, tzinfo=KST)  # 20m drift
    md = _md(last_modified=today_lm, row_count=1000)
    result = evaluate(
        md,
        yesterday_row_count=1000,
        delta_threshold_percent=25.0,
        deadline_time=time(9, 0),
        now=datetime(2026, 5, 7, 6, 0, tzinfo=KST),
        cond_inflow_time_drift=True,
        inflow_drift_threshold_minutes=60,
        baseline_last_modified=yesterday_lm,
    )
    assert all("inflow_drift" not in r for r in result.failure_reasons)


def test_inflow_drift_minutes_returns_clock_time_diff() -> None:
    a = datetime(2026, 5, 7, 5, 0, tzinfo=KST)
    b = datetime(2026, 5, 6, 3, 30, tzinfo=KST)
    assert _inflow_drift_minutes(a, b) == 90


def test_previous_month_window_calculates_first_to_first_of_month() -> None:
    start, end = _previous_month_window(date(2026, 5, 7))
    assert start == datetime(2026, 4, 1, tzinfo=KST)
    assert end == datetime(2026, 5, 1, tzinfo=KST)


def test_previous_month_window_handles_january() -> None:
    start, end = _previous_month_window(date(2026, 1, 15))
    assert start == datetime(2025, 12, 1, tzinfo=KST)
    assert end == datetime(2026, 1, 1, tzinfo=KST)
