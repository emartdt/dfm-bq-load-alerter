from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from dfm_bq_load_alerter.bq.metadata import (
    ConditionQueryError,
    fetch_metadata,
    run_condition_query,
)


def _row(**kwargs):
    obj = MagicMock()
    obj.__getitem__.side_effect = lambda key: kwargs[key]
    return obj


def _scalar_row(value):
    """Single-column BigQuery row stand-in (supports row[0])."""
    obj = MagicMock()
    obj.__getitem__.side_effect = lambda key: value if key == 0 else None
    return obj


def test_fetch_metadata_reads_tables_view_and_skips_count_when_present() -> None:
    client = MagicMock()
    client.project = "emart-datafabric"

    last_mod = datetime(2026, 5, 6, 5, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    metadata_job = MagicMock()
    metadata_job.result.return_value = [_row(last_modified=last_mod, row_count=100)]

    streaming_job = MagicMock()
    streaming_job.result.return_value = [_row(rows=None)]

    client.query.side_effect = [metadata_job, streaming_job]

    meta = fetch_metadata("bw", "PZEVENTID", client=client)

    assert meta.last_modified == last_mod
    assert meta.row_count == 100
    assert meta.used_count_fallback is False
    assert meta.streaming_recent_rows is None
    # exactly two queries: metadata + streaming
    assert client.query.call_count == 2


def test_fetch_metadata_falls_back_to_count_when_row_count_null() -> None:
    client = MagicMock()
    client.project = "emart-datafabric"

    metadata_job = MagicMock()
    metadata_job.result.return_value = [_row(last_modified=None, row_count=None)]
    count_job = MagicMock()
    count_job.result.return_value = [_row(n=42)]
    streaming_job = MagicMock()
    streaming_job.result.return_value = []

    client.query.side_effect = [metadata_job, count_job, streaming_job]

    meta = fetch_metadata("bw", "PZEVENTID", client=client)

    assert meta.row_count == 42
    assert meta.used_count_fallback is True


def test_fetch_metadata_streaming_buffer_added_to_count() -> None:
    client = MagicMock()
    client.project = "emart-datafabric"

    metadata_job = MagicMock()
    metadata_job.result.return_value = [_row(last_modified=None, row_count=100)]
    streaming_job = MagicMock()
    streaming_job.result.return_value = [_row(rows=7)]

    client.query.side_effect = [metadata_job, streaming_job]

    meta = fetch_metadata("bw", "PZEVENTID", client=client)

    assert meta.row_count == 107
    assert meta.streaming_recent_rows == 7
    assert meta.last_modified is not None  # filled from streaming activity


def test_fetch_metadata_streaming_query_failure_is_swallowed() -> None:
    client = MagicMock()
    client.project = "emart-datafabric"

    last_mod = datetime(2026, 5, 6, 5, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    metadata_job = MagicMock()
    metadata_job.result.return_value = [_row(last_modified=last_mod, row_count=100)]

    def query_side_effect(_query, *_args, **_kwargs):
        if query_side_effect.calls == 0:
            query_side_effect.calls += 1
            return metadata_job
        raise RuntimeError("STREAMING_TIMELINE not enabled")

    query_side_effect.calls = 0
    client.query.side_effect = query_side_effect

    meta = fetch_metadata("bw", "PZEVENTID", client=client)

    assert meta.row_count == 100
    assert meta.streaming_recent_rows is None


def _make_client_for_condition_query(
    *, dry_bytes: int, result_value: int | None, exec_bytes: int = 0
):
    """Build a MagicMock client that returns dry-run + execution results."""
    client = MagicMock()
    client.project = "emart-datafabric"
    dry_job = MagicMock()
    dry_job.total_bytes_processed = dry_bytes
    exec_job = MagicMock()
    exec_job.total_bytes_processed = exec_bytes
    if result_value is None:
        exec_job.result.return_value = []
    else:
        exec_job.result.return_value = [_scalar_row(result_value)]
    client.query.side_effect = [dry_job, exec_job]
    return client


def test_run_condition_query_select_returns_int() -> None:
    client = _make_client_for_condition_query(
        dry_bytes=1_000, result_value=42, exec_bytes=900
    )
    rows, used = run_condition_query(
        client,
        query="SELECT COUNT(*) FROM `p.d.t` WHERE flag = TRUE",
        max_bytes=10_000,
    )
    assert rows == 42
    assert used == 900
    assert client.query.call_count == 2


def test_run_condition_query_allows_with_clause() -> None:
    client = _make_client_for_condition_query(
        dry_bytes=500, result_value=7, exec_bytes=500
    )
    rows, _ = run_condition_query(
        client,
        query="WITH x AS (SELECT 1 AS n) SELECT COUNT(*) FROM x",
        max_bytes=10_000,
    )
    assert rows == 7


def test_run_condition_query_rejects_dml_first_token() -> None:
    client = MagicMock()
    with pytest.raises(ConditionQueryError):
        run_condition_query(
            client,
            query="DELETE FROM `p.d.t`",
            max_bytes=10_000,
        )
    assert client.query.call_count == 0


def test_run_condition_query_rejects_forbidden_keyword_inside() -> None:
    client = MagicMock()
    with pytest.raises(ConditionQueryError):
        run_condition_query(
            client,
            query="SELECT 1; DROP TABLE `p.d.t`",
            max_bytes=10_000,
        )
    assert client.query.call_count == 0


def test_run_condition_query_rejects_empty() -> None:
    client = MagicMock()
    with pytest.raises(ConditionQueryError):
        run_condition_query(client, query="   -- only a comment\n", max_bytes=10_000)
    assert client.query.call_count == 0


def test_run_condition_query_dry_run_rejects_over_budget() -> None:
    client = _make_client_for_condition_query(
        dry_bytes=200_000_000, result_value=1
    )
    with pytest.raises(ConditionQueryError):
        run_condition_query(
            client,
            query="SELECT COUNT(*) FROM `p.d.t`",
            max_bytes=100_000_000,
        )
    # dry-run executed, but execution did not
    assert client.query.call_count == 1


def test_fetch_metadata_uses_condition_query_for_row_count() -> None:
    last_mod = datetime(2026, 5, 6, 5, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    client = MagicMock()
    client.project = "emart-datafabric"

    metadata_job = MagicMock()
    metadata_job.result.return_value = [_row(last_modified=last_mod, row_count=100)]
    dry_job = MagicMock()
    dry_job.total_bytes_processed = 500
    cond_job = MagicMock()
    cond_job.total_bytes_processed = 480
    cond_job.result.return_value = [_scalar_row(37)]

    # order: __TABLES__ metadata, dry-run, condition query exec
    client.query.side_effect = [metadata_job, dry_job, cond_job]

    meta = fetch_metadata(
        "bw",
        "PZEVENTID",
        client=client,
        row_count_query="SELECT COUNT(*) FROM `p.d.t` WHERE active",
        row_count_query_max_bytes=10_000,
    )

    assert meta.row_count == 37
    assert meta.last_modified == last_mod
    assert meta.used_count_fallback is False
    # streaming timeline is intentionally skipped when a custom query is used
    assert client.query.call_count == 3
