from __future__ import annotations

from datetime import UTC, date, datetime

import duckdb
import polars as pl

from alpha_lake.canonical import write_bars
from alpha_lake.config import load_config
from alpha_lake.kernel import register_kernel
from alpha_lake.serving import read_bars_asof


def _bar(close: float, eff: str, avail: str) -> pl.DataFrame:
    ts = datetime.fromisoformat(avail)
    eff_d = date.fromisoformat(eff)
    return pl.DataFrame(
        {
            "security_id": ["sec_t"],
            "effective_date": [eff_d],
            "available_at": [ts],
            "source_id": ["eodhd"],
            "open": [close],
            "high": [close * 1.01],
            "low": [close * 0.99],
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


def test_kernel_registers_precedence():
    con = duckdb.connect()
    load_config("config/stack.toml")
    register_kernel(con)
    rows = con.execute("SELECT * FROM _kernel_source_priority ORDER BY priority").fetchall()
    assert len(rows) >= 1
    assert ("bars_daily", "eodhd", 0) in rows or ("bars_daily", "eodhd", 1) in rows
    con.close()


def test_kernel_macro_bars_asof():
    con = duckdb.connect()
    register_kernel(con)
    write_bars(con, _bar(100.0, "2026-01-05", "2026-01-05T16:00:00+00:00"))
    write_bars(con, _bar(200.0, "2026-01-10", "2026-01-10T16:00:00+00:00"))
    result = read_bars_asof(
        con,
        ["sec_t"],
        datetime(2026, 1, 15, tzinfo=UTC),
    ).sort("effective_date")
    assert result.height == 2
    assert result["close"][0] == 100.0
    assert result["close"][1] == 200.0
    con.close()


def test_kernel_macro_respects_asof():
    con = duckdb.connect()
    register_kernel(con)
    write_bars(con, _bar(100.0, "2026-01-05", "2026-01-05T16:00:00+00:00"))
    write_bars(con, _bar(999.0, "2026-01-05", "2026-01-10T16:00:00+00:00"))
    result = read_bars_asof(
        con,
        ["sec_t"],
        datetime(2026, 1, 8, tzinfo=UTC),
    ).sort("effective_date")
    assert result.height == 1
    assert result["close"][0] == 100.0
    con.close()


def test_kernel_macro_date_range():
    con = duckdb.connect()
    register_kernel(con)
    write_bars(con, _bar(100.0, "2026-01-05", "2026-01-05T16:00:00+00:00"))
    write_bars(con, _bar(200.0, "2026-01-10", "2026-01-10T16:00:00+00:00"))
    write_bars(con, _bar(300.0, "2026-01-15", "2026-01-15T16:00:00+00:00"))
    result = read_bars_asof(
        con,
        ["sec_t"],
        datetime(2026, 1, 20, tzinfo=UTC),
        start_date=date(2026, 1, 8),
        end_date=date(2026, 1, 12),
    ).sort("effective_date")
    assert result.height == 1
    assert result["close"][0] == 200.0
    assert result["effective_date"][0] == date(2026, 1, 10)
    con.close()


def _bar_from(close: float, eff: str, avail: str, source: str = "eodhd") -> pl.DataFrame:
    ts = datetime.fromisoformat(avail)
    eff_d = date.fromisoformat(eff)
    return pl.DataFrame(
        {
            "security_id": ["sec_t"],
            "effective_date": [eff_d],
            "available_at": [ts],
            "source_id": [source],
            "open": [close],
            "high": [close * 1.01],
            "low": [close * 0.99],
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


def test_kernel_precedence_wins_over_freshness():
    con = duckdb.connect()
    load_config("config/stack.toml")
    register_kernel(con)
    write_bars(con, _bar_from(100.0, "2026-01-05", "2026-01-05T16:00:00+00:00", "eodhd"))
    write_bars(con, _bar_from(999.0, "2026-01-05", "2026-01-10T16:00:00+00:00", "tiingo"))
    result = read_bars_asof(
        con,
        ["sec_t"],
        datetime(2026, 1, 15, tzinfo=UTC),
    )
    assert result.height == 1
    assert result["close"][0] == 100.0
    con.close()


def test_kernel_empty_result():
    con = duckdb.connect()
    register_kernel(con)
    result = read_bars_asof(
        con,
        ["nonexistent"],
        datetime(2026, 1, 15, tzinfo=UTC),
    )
    assert result.height == 0
    con.close()
