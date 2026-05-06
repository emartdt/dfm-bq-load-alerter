from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from dfm_bq_load_alerter.bq.metadata import fetch_metadata


def _row(**kwargs):
    obj = MagicMock()
    obj.__getitem__.side_effect = lambda key: kwargs[key]
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
