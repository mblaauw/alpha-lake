from datetime import date, datetime

import duckdb
import polars as pl
import pytest

from alpha_lake.canonical import write_bars
from alpha_lake.serving import read_bars_asof


def _df(
    close_val: float,
    effective: str,
    available: str,
) -> pl.DataFrame:
    ts = datetime.fromisoformat(available)
    return pl.DataFrame({
        "security_id": ["sec_t"], "effective_date": [date.fromisoformat(effective)],
        "available_at": [ts], "source_id": ["eodhd"],
        "open": [100.0], "high": [101.0], "low": [99.0], "close": [close_val],
        "volume": [10000], "source_fetch_id": [""], "raw_payload_hash": [""],
        "ingestion_run_id": [""], "content_hash": [""], "version_hash": [""],
        "schema_version": [1], "parser_version": [1], "quality_status": ["valid"],
        "source_published_at": [None], "ingested_at": [None], "validated_at": [None],
    }).with_columns(
        pl.col("source_published_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("ingested_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("validated_at").cast(pl.Datetime(time_zone="UTC")),
    )


@pytest.fixture
def con():
    c = duckdb.connect()
    yield c
    c.close()


def test_available_at_must_be_less_than_as_of(con):
    df = _df(100.0, "2026-01-05", "2026-01-10")
    write_bars(con, df)
    result = read_bars_asof(con, ["sec_t"], datetime(2026, 1, 9, 12, 0))
    assert result.height == 0, "row with available_at > as_of must not be visible"


def test_available_at_equal_to_as_of_is_visible(con):
    df = _df(100.0, "2026-01-05", "2026-01-10")
    write_bars(con, df)
    result = read_bars_asof(con, ["sec_t"], datetime(2026, 1, 10, 12, 0))
    assert result.height == 1, "row with available_at <= as_of must be visible"
    assert result["close"][0] == 100.0


def test_newest_version_wins(con):
    write_bars(con, _df(100.0, "2026-01-05", "2026-01-10"))
    write_bars(con, _df(101.0, "2026-01-05", "2026-01-11"))
    result = read_bars_asof(con, ["sec_t"], datetime(2026, 1, 12, 12, 0))
    assert result["close"][0] == 101.0, "newest visible version must be returned"


def test_older_as_of_sees_older_version(con):
    write_bars(con, _df(100.0, "2026-01-05", "2026-01-10"))
    write_bars(con, _df(101.0, "2026-01-05", "2026-01-11"))
    result = read_bars_asof(con, ["sec_t"], datetime(2026, 1, 10, 12, 0))
    assert result["close"][0] == 100.0, "older as_of must see older version"


def test_multiple_securities_independent_visibility(con):
    df1 = pl.DataFrame({
        "security_id": ["sec_a", "sec_b"],
        "effective_date": [date(2026, 1, 5), date(2026, 1, 5)],
        "available_at": [datetime(2026, 1, 10), datetime(2026, 1, 11)],
        "source_id": ["eodhd", "eodhd"],
        "open": [100.0, 200.0], "high": [101.0, 201.0], "low": [99.0, 199.0],
        "close": [100.5, 200.5], "volume": [10000, 20000],
        "source_fetch_id": ["", ""], "raw_payload_hash": ["", ""],
        "ingestion_run_id": ["", ""], "content_hash": ["", ""],
        "version_hash": ["", ""], "schema_version": [1, 1],
        "parser_version": [1, 1], "quality_status": ["valid", "valid"],
        "source_published_at": [None, None], "ingested_at": [None, None],
        "validated_at": [None, None],
    }).with_columns(
        pl.col("source_published_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("ingested_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("validated_at").cast(pl.Datetime(time_zone="UTC")),
    )
    write_bars(con, df1)
    result = read_bars_asof(con, ["sec_a", "sec_b"], datetime(2026, 1, 10, 12, 0))
    assert result.height == 1, "only sec_a visible (sec_b available_at is later)"
    assert result["security_id"][0] == "sec_a"
