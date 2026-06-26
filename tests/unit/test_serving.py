from datetime import UTC, date, datetime

import duckdb
import polars as pl
import pytest

from alpha_lake.canonical import write_bars
from alpha_lake.derived import ema, returns, sma
from alpha_lake.kernel import register_kernel
from alpha_lake.serving import read_asof_join, read_bars_latest, read_panel


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


def test_read_bars_latest():
    con = duckdb.connect()
    register_kernel(con)
    write_bars(con, _bar(100.0, "2026-01-05", "2026-01-05T16:00:00+00:00"))
    result = read_bars_latest(con, ["sec_t"])
    assert result.height == 1
    con.close()


def test_read_panel():
    con = duckdb.connect()
    register_kernel(con)
    write_bars(con, _bar(100.0, "2026-01-05", "2026-01-05T16:00:00+00:00"))
    spine = pl.DataFrame(
        {
            "security_id": ["sec_t"],
            "effective_date": [date(2026, 1, 10)],
        }
    )
    result = read_panel(con, spine, datetime(2026, 1, 15, tzinfo=UTC))
    assert result.height == 1
    assert result["close"][0] == 100.0
    con.close()


def test_read_asof_join():
    con = duckdb.connect()
    register_kernel(con)
    write_bars(con, _bar(100.0, "2026-01-05", "2026-01-05T16:00:00+00:00"))
    write_bars(con, _bar(200.0, "2026-01-10", "2026-01-10T16:00:00+00:00"))
    spine = pl.DataFrame(
        {
            "security_id": ["sec_t", "sec_t"],
            "effective_date": [date(2026, 1, 5), date(2026, 1, 10)],
            "as_of": [datetime(2026, 1, 6, tzinfo=UTC), datetime(2026, 1, 15, tzinfo=UTC)],
        }
    )
    result = read_asof_join(con, spine).sort("effective_date")
    assert result.height == 2
    assert result["close"][0] == 100.0
    assert result["close"][1] == 200.0
    con.close()


