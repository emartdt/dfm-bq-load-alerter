"""Tables API 스키마 검증 — project_id 필수화 (DPC-1583).

빈 project_id 로 등록된 테이블이 점검 시점에야 "BigQuery 호출 실패" 로
드러나는 문제를 등록 시점 검증으로 차단한다.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from dfm_bq_load_alerter.api.tables import (
    BulkTablesIn,
    ConditionQueryPreviewIn,
    TableIn,
    TablePatch,
)

VALID_TABLE = {
    "dataset": "ds",
    "table_name": "t1",
    "frequency": "daily",
    "batch_time": "05:00",
}


def test_table_in_requires_project_id() -> None:
    with pytest.raises(ValidationError):
        TableIn(**VALID_TABLE)


def test_table_in_rejects_empty_project_id() -> None:
    with pytest.raises(ValidationError):
        TableIn(project_id="", **VALID_TABLE)


def test_table_in_accepts_project_id() -> None:
    table = TableIn(project_id="my-project", **VALID_TABLE)
    assert table.project_id == "my-project"


def test_table_patch_rejects_explicit_null_project_id() -> None:
    with pytest.raises(ValidationError):
        TablePatch(project_id=None)


def test_table_patch_allows_omitted_project_id() -> None:
    patch = TablePatch(note="memo")
    assert "project_id" not in patch.model_dump(exclude_unset=True)


def test_table_patch_accepts_project_id() -> None:
    patch = TablePatch(project_id="my-project")
    assert patch.project_id == "my-project"


def test_bulk_tables_in_requires_project_id() -> None:
    with pytest.raises(ValidationError):
        BulkTablesIn(
            dataset="ds",
            tables={"t1": {"time": "05:00", "type": "daily"}},
        )


def test_bulk_tables_in_accepts_project_id() -> None:
    bulk = BulkTablesIn(
        project_id="my-project",
        dataset="ds",
        tables={"t1": {"time": "05:00", "type": "daily"}},
    )
    assert bulk.project_id == "my-project"


def test_condition_query_preview_requires_project_id() -> None:
    with pytest.raises(ValidationError):
        ConditionQueryPreviewIn(query="SELECT 1")


def test_condition_query_preview_accepts_project_id() -> None:
    payload = ConditionQueryPreviewIn(query="SELECT 1", project_id="my-project")
    assert payload.project_id == "my-project"
