from __future__ import annotations

import polars as pl


def sma(series: pl.Series, window: int) -> pl.Series:
    """Simple moving average."""
    return series.rolling_mean(window_size=window)


def ema(series: pl.Series, window: int) -> pl.Series:
    """Exponential moving average."""
    alpha = 2.0 / (window + 1)
    return series.ewm_mean(alpha=alpha, adjust=False)


def rsi(series: pl.Series, window: int = 14) -> pl.Series:
    """Relative Strength Index (Wilder's smoothing)."""
    delta = series.diff()
    gain = delta * (delta > 0).cast(pl.Float64)
    loss = (-delta) * (delta < 0).cast(pl.Float64)
    avg_gain = gain.rolling_mean(window_size=window, min_samples=1)
    avg_loss = loss.rolling_mean(window_size=window, min_samples=1)
    rs = avg_gain / avg_loss
    rs = rs.fill_nan(100.0).fill_null(100.0)
    return 100 - (100 / (1 + rs))


def bollinger_bands(series: pl.Series, window: int = 20, num_std: float = 2.0) -> dict[str, pl.Series]:
    """Bollinger Bands: middle (SMA), upper, lower."""
    middle = sma(series, window)
    std = series.rolling_std(window_size=window)
    return {
        "middle": middle,
        "upper": middle + std * num_std,
        "lower": middle - std * num_std,
    }


def atr(high: pl.Series, low: pl.Series, close: pl.Series, window: int = 14) -> pl.Series:
    """Average True Range."""
    tr = pl.DataFrame({
        "h_l": high - low,
        "h_c": (high - close.shift(1)).abs(),
        "l_c": (low - close.shift(1)).abs(),
    }).select(pl.max_horizontal("h_l", "h_c", "l_c")).to_series()
    return tr.rolling_mean(window_size=window)


def obv(close: pl.Series, volume: pl.Series) -> pl.Series:
    """On-Balance Volume."""
    up = close > close.shift(1)
    down = close < close.shift(1)
    direction = (volume * up.cast(pl.Float64)) - (volume * down.cast(pl.Float64))
    direction[0] = volume[0]
    return direction.cum_sum()


def vwap(high: pl.Series, low: pl.Series, close: pl.Series, volume: pl.Series) -> pl.Series:
    """Volume-Weighted Average Price."""
    typical = (high + low + close) / 3
    cum_pv = (typical * volume).cum_sum()
    cum_v = volume.cum_sum()
    return cum_pv / cum_v


def macd(series: pl.Series, fast: int = 12, slow: int = 26, signal_period: int = 9) -> dict[str, pl.Series]:
    """MACD line, signal line, histogram."""
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal_period)
    histogram = macd_line - signal_line
    return {"macd": macd_line, "signal_line": signal_line, "histogram": histogram}
