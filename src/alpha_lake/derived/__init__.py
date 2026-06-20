from __future__ import annotations

import polars as pl

from alpha_lake.derived.indicators import (
    atr,
    bollinger_bands,
    ema,
    macd,
    obv,
    rsi,
    sma,
    vwap,
)


def typical_price(df: pl.DataFrame) -> pl.Series:
    """(high + low + close) / 3"""
    return (df["high"] + df["low"] + df["close"]) / 3


def returns(df: pl.DataFrame, period: int = 1) -> pl.Series:
    """Simple period-over-period returns: close / close.shift(period) - 1."""
    return df["close"] / df["close"].shift(period) - 1


