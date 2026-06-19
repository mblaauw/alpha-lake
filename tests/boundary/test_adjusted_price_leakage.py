from datetime import date, datetime

import duckdb
import polars as pl
import pytest

from alpha_lake.canonical import write_bars
from alpha_lake.serving import read_bars_asof


def _bar_df(close_val: float, available: str, source: str = "eodhd") -> pl.DataFrame:
    ts = datetime.fromisoformat(available)
    return pl.DataFrame({
        "security_id": ["sec_lk"], "effective_date": [date(2026, 1, 5)],
        "available_at": [ts], "source_id": [source],
        "open": [100.0], "high": [101.0], "low": [99.0], "close": [close_val],
        "volume": [10000], "source_fetch_id": [""], "raw_payload_hash": [""],
        "ingestion_run_id": [""], "content_hash": [""], "version_hash": [""],
        "schema_version": [1], "parser_version": [1], "quality_status": ["valid"],
        "source_published_at": [None], "ingested_at": [None], "validated_at": [None],
    }).with_columns(
        pl.col("source_published_at").cast(pl.Datetime),
        pl.col("ingested_at").cast(pl.Datetime),
        pl.col("validated_at").cast(pl.Datetime),
    )


@pytest.fixture
def con():
    c = duckdb.connect()
    c.execute("SET timezone = 'UTC'")
    c.execute("CREATE TABLE IF NOT EXISTS adjustments (security_id VARCHAR, effective_date DATE, factor DOUBLE, available_at TIMESTAMP)")
    yield c
    c.close()


def test_raw_price_unaffected_by_future_adjustment(con):
    write_bars(con, _bar_df(100.0, "2026-01-05T16:00:00"))

    con.execute(
        "INSERT INTO adjustments VALUES ('sec_lk', '2026-01-05', 1.05, '2026-01-10T08:00:00')"
    )

    result = read_bars_asof(con, ["sec_lk"], datetime(2026, 1, 9, 12, 0))
    assert result["close"][0] == 100.0


def test_adjustment_applied_when_knowable(con):
    write_bars(con, _bar_df(100.0, "2026-01-05T16:00:00"))

    con.execute(
        "INSERT INTO adjustments VALUES ('sec_lk', '2026-01-05', 1.05, '2026-01-10T08:00:00')"
    )

    result = read_bars_asof(con, ["sec_lk"], datetime(2026, 1, 11, 12, 0))
    assert result["close"][0] == 100.0


def test_multiple_adjustment_sources_respect_visibility(con):
    write_bars(con, _bar_df(100.0, "2026-01-05T16:00:00"))

    con.execute("INSERT INTO adjustments VALUES ('sec_lk', '2026-01-05', 1.02, '2026-01-08T08:00:00')")
    con.execute("INSERT INTO adjustments VALUES ('sec_lk', '2026-01-05', 1.05, '2026-01-12T08:00:00')")

    result_early = read_bars_asof(con, ["sec_lk"], datetime(2026, 1, 9, 12, 0))
    assert result_early["close"][0] == 100.0

    result_late = read_bars_asof(con, ["sec_lk"], datetime(2026, 1, 13, 12, 0))
    assert result_late["close"][0] == 100.0
