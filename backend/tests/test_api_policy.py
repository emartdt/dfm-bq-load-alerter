"""Alert Policy / History API smoke + validators (PR-D)."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from dfm_bq_load_alerter.api.policy import _validate_check_times


def test_validate_check_times_accepts_canonical() -> None:
    _validate_check_times(["06:00", "07:00", "08:20"])


def test_validate_check_times_rejects_garbage() -> None:
    with pytest.raises(HTTPException) as excinfo:
        _validate_check_times(["06:00", "not-a-time"])
    assert excinfo.value.status_code == 422


def test_history_router_registered() -> None:
    from dfm_bq_load_alerter.main import app

    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]
    assert "/api/history/snapshots" in paths
    assert "/api/history/events" in paths
    assert "/api/history/stats/daily" in paths
    assert "/api/history/stats/monthly" in paths
    assert "/api/history/stats/table-success-rate" in paths


def test_policy_router_registered() -> None:
    from dfm_bq_load_alerter.main import app

    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]
    assert "/api/policy" in paths
