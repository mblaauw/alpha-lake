from datetime import date, datetime

import polars as pl

from alpha_lake.canonical import write_bars
from alpha_lake.harness import EmbeddedHarness
from alpha_lake.serving import read_bars_asof
from tests.fixtures import golden_hash


def test_embedded_produces_deterministic_output():
    h1 = EmbeddedHarness()
    h1.start()
    result1 = _run_full_pipeline(h1)
    h1.stop()

    h2 = EmbeddedHarness()
    h2.start()
    result2 = _run_full_pipeline(h2)
    h2.stop()

    assert result1 == result2, "two embedded runs with same inputs must produce identical hash"


def test_embedded_output_matches_golden_fixture():
    h = EmbeddedHarness()
    h.start()
    result = _run_full_pipeline(h)
    h.stop()

    assert result == golden_hash(), "embedded run must match frozen golden hash"


def test_harness_cleanup_removes_temp_dir():
    import os
    h = EmbeddedHarness()
    h.start()
    path = h.data_path
    assert os.path.exists(path)
    h.stop()
    assert not os.path.exists(path), "harness stop must clean up temp directory"


def _run_full_pipeline(harness: EmbeddedHarness) -> str:
    import hashlib, json
    from alpha_lake.replay import _canonical_hash as canonical_hash

    df = pl.DataFrame({
        "security_id": ["sec_aap"], "effective_date": [date(2026, 1, 5)],
        "available_at": [datetime(2026, 1, 5, 16, 0, 0)],
        "source_id": ["eodhd"], "open": [200.0], "high": [205.0], "low": [199.0], "close": [203.5],
        "volume": [5000000], "source_fetch_id": ["f1"], "raw_payload_hash": ["h1"],
        "ingestion_run_id": ["r1"], "content_hash": ["c1"], "version_hash": [""],
        "schema_version": [1], "parser_version": [1], "quality_status": ["valid"],
        "source_published_at": [None], "ingested_at": [None], "validated_at": [None],
    }).with_columns(
        pl.col("source_published_at").cast(pl.Datetime),
        pl.col("ingested_at").cast(pl.Datetime),
        pl.col("validated_at").cast(pl.Datetime),
    )

    write_bars(harness.conn, df)
    result = read_bars_asof(harness.conn, ["sec_aap"], datetime(2026, 1, 5, 17, 0, 0))
    rows = json.loads(result.write_json())
    return canonical_hash(rows)
