from datetime import UTC, date, datetime

import duckdb
import polars as pl

from alpha_lake.canonical import write_bars
from alpha_lake.config import load_config
from alpha_lake.flows import _missing_dates, compact_dataset, ingest_bars, reparse_bars


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
    assert _r is not None
    assert _r[0] == 1

    count = reparse_bars(con, ["sec_test"])
    assert count == 1

    _r = con.execute(
        "SELECT COUNT(*), COUNT(DISTINCT available_at) "
        "FROM lake_bars WHERE security_id = 'sec_test'"
    ).fetchone()
    assert _r is not None
    assert _r[0] == 2, "reparse must create a second version"
    assert _r[1] == 2, "second version must have different available_at"
    con.close()


def test_compact_dataset():
    load_config("config/embedded.toml")
    con = duckdb.connect()
    df1 = pl.DataFrame(
        {
            "security_id": ["sec_t"],
            "effective_date": [date(2026, 1, 5)],
            "available_at": [datetime(2026, 1, 5, 16, 0, tzinfo=UTC)],
            "source_id": ["eodhd"],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [10000],
            "source_fetch_id": [""],
            "raw_payload_hash": [""],
            "ingestion_run_id": [""],
            "content_hash": [""],
            "version_hash": [""],
            "schema_version": [1],
            "parser_version": [1],
            "quality_status": ["valid"],
            "source_published_at": [None],
            "ingested_at": [None],
            "validated_at": [None],
        }
    ).with_columns(
        pl.col("source_published_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("ingested_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("validated_at").cast(pl.Datetime(time_zone="UTC")),
    )
    write_bars(con, df1)
    count = compact_dataset(con, "lake_bars")
    assert count == 1
    con.close()


def test_missing_dates_empty_table():
    load_config("config/embedded.toml")
    con = duckdb.connect()
    # Table doesn't exist yet — should return the requested range
    result = _missing_dates(con, "lake_bars", "sec_test", "2026-01-05", "2026-01-07")
    assert result == ["2026-01-05", "2026-01-06", "2026-01-07"]
    con.close()


def test_missing_dates_no_bounds_returns_today_when_empty():
    load_config("config/embedded.toml")
    con = duckdb.connect()
    result = _missing_dates(con, "lake_bars", "sec_test")
    assert result == [date.today().isoformat()]
    con.close()


def test_missing_dates_no_bounds_returns_empty_when_data_exists():
    load_config("config/embedded.toml")
    con = duckdb.connect()
    ingest_bars(con, ["sec_test"], "2026-01-05", "2026-01-05", source_id="eodhd")
    result = _missing_dates(con, "lake_bars", "sec_test")
    assert result == []
    con.close()


def test_missing_dates_fully_covered():
    load_config("config/embedded.toml")
    con = duckdb.connect()
    ingest_bars(con, ["sec_test"], "2026-01-05", "2026-01-05", source_id="eodhd")
    result = _missing_dates(con, "lake_bars", "sec_test", "2026-01-05", "2026-01-05")
    assert result == []
    con.close()


def test_missing_dates_partially_covered():
    load_config("config/embedded.toml")
    con = duckdb.connect()
    ingest_bars(con, ["sec_test"], "2026-01-05", "2026-01-05", source_id="eodhd")
    result = _missing_dates(con, "lake_bars", "sec_test", "2026-01-05", "2026-01-10")
    assert "2026-01-05" not in result
    for d in ("2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09", "2026-01-10"):
        assert d in result
    con.close()


def test_missing_dates_after_existing_range():
    load_config("config/embedded.toml")
    con = duckdb.connect()
    ingest_bars(con, ["sec_test"], "2026-01-05", "2026-01-05", source_id="eodhd")
    result = _missing_dates(con, "lake_bars", "sec_test", "2026-01-10", "2026-01-12")
    assert result == ["2026-01-10", "2026-01-11", "2026-01-12"]
    con.close()


def test_ingest_bars_is_idempotent():
    load_config("config/embedded.toml")
    con = duckdb.connect()
    count1 = ingest_bars(con, ["sec_test"], "2026-01-05", "2026-01-05", source_id="eodhd")
    assert count1 == 1
    _r = con.execute("SELECT COUNT(*) FROM lake_bars").fetchone()
    assert _r is not None
    assert _r[0] == 1
    # Second call for same date should return 0 (no new rows)
    count2 = ingest_bars(con, ["sec_test"], "2026-01-05", "2026-01-05", source_id="eodhd")
    assert count2 == 0
    _r = con.execute("SELECT COUNT(*) FROM lake_bars").fetchone()
    assert _r is not None
    assert _r[0] == 1, "no new rows should be inserted"
    con.close()


def test_ingest_bars_idempotent_partial_overlap():
    load_config("config/embedded.toml")
    con = duckdb.connect()
    count1 = ingest_bars(con, ["sec_test"], "2026-01-05", "2026-01-07", source_id="eodhd")
    assert count1 == 1  # synthetic generates 1 bar
    _r = con.execute("SELECT COUNT(*) FROM lake_bars").fetchone()
    assert _r is not None
    assert _r[0] == 1
    # Second call with overlapping + new dates
    count2 = ingest_bars(con, ["sec_test"], "2026-01-07", "2026-01-10", source_id="eodhd")
    assert count2 == 1  # synthetic generates 1 bar for Jan 7 (first missing date)
    _r = con.execute("SELECT COUNT(*) FROM lake_bars").fetchone()
    assert _r is not None
    assert _r[0] == 2  # Jan 5 + Jan 7
    con.close()


def test_ingest_bars_empty_security():
    """Ingesting a security for dates that already exist should return 0."""
    load_config("config/embedded.toml")
    con = duckdb.connect()
    count1 = ingest_bars(con, ["sec_test"], "2026-01-05", "2026-01-05", source_id="eodhd")
    assert count1 == 1
    # Same security, same range — should skip
    count2 = ingest_bars(con, ["sec_test"], "2026-01-05", "2026-01-05", source_id="eodhd")
    assert count2 == 0
    con.close()


def test_compact_dataset_dedup():
    load_config("config/embedded.toml")
    con = duckdb.connect()
    avail_at = datetime(2026, 1, 5, 16, 0, tzinfo=UTC)
    df = pl.DataFrame(
        {
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
        }
    ).with_columns(
        pl.col("source_published_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("ingested_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("validated_at").cast(pl.Datetime(time_zone="UTC")),
    )
    write_bars(con, df)
    _r = con.execute("SELECT COUNT(*) FROM lake_bars").fetchone()
    assert _r is not None
    assert _r[0] == 3
    count = compact_dataset(con, "lake_bars")
    assert count == 1
    con.close()
