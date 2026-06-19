import json
from datetime import datetime, timezone

import polars as pl

from alpha_lake.models.bar_fact import BarFact
from alpha_lake.normalize import bars_from_json


def test_normalize_produces_valid_barfact():
    sample_response = [
        {"date": "2026-01-05", "open": 200.0, "high": 205.0, "low": 199.0, "close": 203.5, "volume": 5000000},
    ]
    ts = datetime(2026, 1, 5, 16, 0, 0, tzinfo=timezone.utc)
    df = bars_from_json(sample_response, "sec_test", "eodhd", "fetch_1", "run_1", "abc123", ts)
    validated = BarFact.validate(df)
    assert validated.height == 1
    assert validated["security_id"][0] == "sec_test"
    assert validated["close"][0] == 203.5
    assert validated["volume"][0] == 5000000


def test_normalize_missing_optional_fields():
    sample_response = [
        {"date": "2026-01-05", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5},
    ]
    ts = datetime(2026, 1, 5, 16, 0, 0)
    df = bars_from_json(sample_response, "sec_test", "eodhd", "fetch_1", "run_1", "abc123", ts)
    validated = BarFact.validate(df)
    assert validated["volume"][0] == 0


def test_manifest_structure():
    from alpha_lake.connectors.base import build_manifest
    manifest = build_manifest("eodhd", "/eod/AAPL.US", {"period": "d"}, b"test data", 200, 1)
    assert manifest["source_id"] == "eodhd"
    assert manifest["http_status"] == 200
    assert manifest["content_hash"]
    assert manifest["request_params_hash"]
    assert manifest["byte_size"] == 9


def test_raw_archive_roundtrip():
    from alpha_lake.config import load_config
    from alpha_lake.raw import archive, read_raw
    load_config("config/embedded.toml")
    data = b'{"date":"2026-01-05","open":200.0}'
    h = archive(data)
    restored = read_raw(h)
    assert restored == data
    assert json.loads(restored)["open"] == 200.0


def test_canonical_write_contract():
    from datetime import date
    import duckdb
    from alpha_lake.canonical import write_bars
    con = duckdb.connect()
    df = pl.DataFrame({
        "security_id": ["sec_test"], "effective_date": [date(2026, 6, 18)],
        "available_at": [datetime(2026, 6, 18, 16, 0, 0)],
        "source_id": ["eodhd"], "open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5],
        "volume": [10000], "source_fetch_id": [""], "raw_payload_hash": [""], "ingestion_run_id": [""],
        "content_hash": [""], "version_hash": [""], "schema_version": [1], "parser_version": [1],
        "quality_status": ["valid"],
        "source_published_at": [None], "ingested_at": [None], "validated_at": [None],
    }).with_columns(
        pl.col("source_published_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("ingested_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("validated_at").cast(pl.Datetime(time_zone="UTC")),
    )
    count = write_bars(con, df)
    assert count == 1
    result = con.execute("SELECT close FROM lake_bars WHERE security_id='sec_test'").fetchone()[0]
    assert result == 100.5
    con.close()
