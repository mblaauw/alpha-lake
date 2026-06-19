from __future__ import annotations

from datetime import date, datetime

import duckdb
import polars as pl

from alpha_lake.derived.indicators import bollinger_bands, macd, rsi, sma
from alpha_lake.serving import read_bars_asof


def compute_indicator(
    con: duckdb.DuckDBPyConnection,
    security_id: str,
    indicator: str,
    as_of: datetime,
    window: int = 20,
    start_date: date | None = None,
    end_date: date | None = None,
) -> pl.DataFrame | dict:
    """Compute a PIT-bounded technical indicator.

    Args:
        indicator: 'sma', 'rsi', 'bollinger', 'macd', 'vwap'
    """
    bars = read_bars_asof(con, [security_id], as_of, start_date, end_date)
    if bars.height == 0:
        return pl.DataFrame()

    bars = bars.sort("effective_date")
    close = bars["close"]

    if indicator == "sma":
        vals = sma(close, window)
        return bars.with_columns(pl.Series(f"sma_{window}", vals))

    if indicator == "rsi":
        vals = rsi(close, window)
        return bars.with_columns(pl.Series(f"rsi_{window}", vals))

    if indicator == "bollinger":
        bands = bollinger_bands(close, window)
        return bars.with_columns(
            pl.Series("bb_middle", bands["middle"]),
            pl.Series("bb_upper", bands["upper"]),
            pl.Series("bb_lower", bands["lower"]),
        )

    if indicator == "macd":
        m = macd(close)
        return bars.with_columns(
            pl.Series("macd", m["macd"]),
            pl.Series("macd_signal", m["signal"]),
            pl.Series("macd_histogram", m["histogram"]),
        )

    raise ValueError(f"Unknown indicator: {indicator}")
