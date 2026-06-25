from __future__ import annotations

import polars as pl

from alpha_lake.derived.fundamental_metrics import (
    compute_estimate_metrics,
    compute_fundamental_period_metrics,
)
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

__all__ = [
    "atr",
    "bollinger_bands",
    "compute_estimate_metrics",
    "compute_fundamental_period_metrics",
    "ema",
    "macd",
    "obv",
    "rsi",
    "sma",
    "vwap",
    "typical_price",
    "returns",
]


def typical_price(df: pl.DataFrame) -> pl.Series:
    """(high + low + close) / 3"""
    return (df["high"] + df["low"] + df["close"]) / 3


def returns(df: pl.DataFrame, period: int = 1) -> pl.Series:
    """Simple period-over-period returns: close / close.shift(period) - 1."""
    return df["close"] / df["close"].shift(period) - 1
