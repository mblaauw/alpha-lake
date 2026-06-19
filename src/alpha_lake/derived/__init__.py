from __future__ import annotations

import polars as pl


def typical_price(df: pl.DataFrame) -> pl.Series:
    """(high + low + close) / 3"""
    return (df["high"] + df["low"] + df["close"]) / 3


def returns(df: pl.DataFrame, period: int = 1) -> pl.Series:
    """Simple period-over-period returns: close / close.shift(period) - 1."""
    return df["close"] / df["close"].shift(period) - 1


def sma(df: pl.DataFrame, window: int) -> pl.Series:
    """Simple moving average of close."""
    return df["close"].rolling_mean(window_size=window)


def ema(df: pl.DataFrame, window: int) -> pl.Series:
    """Exponential moving average of close."""
    alpha = 2.0 / (window + 1)
    result = [df["close"][0]]
    for val in df["close"][1:]:
        result.append(alpha * val + (1 - alpha) * result[-1])
    return pl.Series(result)
