from datetime import UTC, date, datetime

import duckdb
import polars as pl

from alpha_lake.canonical import write_bars, write_corp_actions
from alpha_lake.normalize.corp_actions import splits_from_json
from alpha_lake.serving import read_bars_adjusted


def _bar(close: float) -> pl.DataFrame:
    ts = datetime(2025, 6, 1, 16, 0, tzinfo=UTC)
    return pl.DataFrame(
        {
            "security_id": ["sec_test"],
            "effective_date": [date(2025, 5, 15)],
            "available_at": [ts],
            "source_id": ["eodhd"],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [close],
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


def test_raw_mode_returns_unadjusted():
    con = duckdb.connect()
    write_bars(con, _bar(100.0))
    result = read_bars_adjusted(
        con,
        ["sec_test"],
        datetime(2025, 6, 15, tzinfo=UTC),
        price_mode="raw",
    )
    assert result["close"][0] == 100.0
    assert "adjustment_factor" not in result.columns
    con.close()


def test_split_adjusted_reduces_price():
    con = duckdb.connect()
    write_bars(con, _bar(100.0))

    as_of = datetime(2025, 6, 15, tzinfo=UTC)
    split_data = splits_from_json(
        [{"date": "2025-06-01", "splitRatio": "2:1"}],
        "sec_test",
        "eodhd_splits",
        "f1",
        "r1",
        "c1",
        datetime(2025, 6, 2, tzinfo=UTC),
    )
    write_corp_actions(con, split_data)

    result = read_bars_adjusted(con, ["sec_test"], as_of, price_mode="split_adjusted")
    assert result["close"][0] == 50.0  # 100 / (2/1) = 50
    assert result["adjustment_factor"][0] == 2.0
    con.close()


def test_adjustment_respects_pit_boundary():
    con = duckdb.connect()
    write_bars(con, _bar(100.0))

    split_ts = datetime(2025, 6, 5, tzinfo=UTC)
    split_data = splits_from_json(
        [{"date": "2025-06-01", "splitRatio": "2:1"}],
        "sec_test",
        "eodhd_splits",
        "f1",
        "r1",
        "c1",
        split_ts,
    )
    write_corp_actions(con, split_data)

    as_of_before = datetime(2025, 6, 3, tzinfo=UTC)
    raw_mode = read_bars_adjusted(con, ["sec_test"], as_of_before, price_mode="split_adjusted")
    assert raw_mode["close"][0] == 100.0  # split not yet knowable

    as_of_after = datetime(2025, 6, 15, tzinfo=UTC)
    adj_mode = read_bars_adjusted(con, ["sec_test"], as_of_after, price_mode="split_adjusted")
    assert adj_mode["close"][0] == 50.0  # split now knowable
    con.close()
