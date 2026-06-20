from datetime import date, datetime, timezone

import duckdb
import polars as pl

from alpha_lake.canonical import write_bars
from alpha_lake.config import load_config
from alpha_lake.flows import compact_dataset, ingest_bars, reparse_bars


def test_ingest_bars():
    load_config("config/embedded.toml")
    con = duckdb.connect()
    count = ingest_bars(con, ["sec_test"], "2026-01-05", "2026-01-05", source_id="eodhd")
    assert count == 1
    _r = con.execute("SELECT COUNT(*) FROM lake_bars").fetchone()
    rows = _r[0] if _r else 0
    assert rows == 1
    con.close()


def test_reparse_bars():
    load_config("config/embedded.toml")
    con = duckdb.connect()
    ingest_bars(con, ["sec_test"], "2026-01-05", "2026-01-05", source_id="eodhd")
    _r = con.execute("SELECT COUNT(*) FROM lake_bars").fetchone()
    assert _r[0] == 1

    count = reparse_bars(con, ["sec_test"])
    assert count == 1

    _r = con.execute("SELECT COUNT(*), COUNT(DISTINCT available_at) FROM lake_bars WHERE security_id = 'sec_test'").fetchone()
    assert _r[0] == 2, "reparse must create a second version"
    assert _r[1] == 2, "second version must have different available_at"
    con.close()


def test_compact_dataset():
    load_config("config/embedded.toml")
    con = duckdb.connect()
    df1 = pl.DataFrame({
        "security_id": ["sec_t"], "effective_date": [date(2026, 1, 5)],
        "available_at": [datetime(2026, 1, 5, 16, 0, tzinfo=timezone.utc)],
        "source_id": ["eodhd"], "open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5],
        "volume": [10000], "source_fetch_id": [""], "raw_payload_hash": [""],
        "ingestion_run_id": [""], "content_hash": [""], "version_hash": [""],
        "schema_version": [1], "parser_version": [1], "quality_status": ["valid"],
        "source_published_at": [None], "ingested_at": [None], "validated_at": [None],
    }).with_columns(
        pl.col("source_published_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("ingested_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("validated_at").cast(pl.Datetime(time_zone="UTC")),
    )
    write_bars(con, df1)
    count = compact_dataset(con, "lake_bars")
    assert count == 1
    con.close()


def test_compact_dataset_dedup():
    load_config("config/embedded.toml")
    con = duckdb.connect()
    avail_at = datetime(2026, 1, 5, 16, 0, tzinfo=timezone.utc)
    df = pl.DataFrame({
        "security_id": ["sec_t"] * 3,
        "effective_date": [date(2026, 1, 5)] * 3,
        "available_at": [avail_at] * 3,
        "source_id": ["eodhd"] * 3,
        "open": [100.0, 100.0, 100.0],
        "high": [101.0, 101.0, 101.0],
        "low": [99.0, 99.0, 99.0],
        "close": [100.5, 100.5, 100.5],
        "volume": [10000, 10000, 10000],
        "source_fetch_id": ["", "", ""],
        "raw_payload_hash": ["", "", ""],
        "ingestion_run_id": ["", "", ""],
        "content_hash": ["", "", ""],
        "version_hash": ["", "", ""],
        "schema_version": [1, 1, 1],
        "parser_version": [1, 1, 1],
        "quality_status": ["valid", "valid", "valid"],
        "source_published_at": [None, None, None],
        "ingested_at": [None, None, None],
        "validated_at": [None, None, None],
    }).with_columns(
        pl.col("source_published_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("ingested_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("validated_at").cast(pl.Datetime(time_zone="UTC")),
    )
    write_bars(con, df)
    _r = con.execute("SELECT COUNT(*) FROM lake_bars").fetchone()
    assert _r[0] == 3
    count = compact_dataset(con, "lake_bars")
    assert count == 1
    con.close()
