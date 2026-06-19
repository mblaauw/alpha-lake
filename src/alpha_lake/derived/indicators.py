from __future__ import annotations

import polars as pl


def sma(series: pl.Series, window: int) -> pl.Series:
    """Simple moving average."""
    return series.rolling_mean(window_size=window)


def ema(series: pl.Series, window: int) -> pl.Series:
    """Exponential moving average."""
    alpha = 2.0 / (window + 1)
    result = [series[0]]
    for val in series[1:]:
        result.append(alpha * val + (1 - alpha) * result[-1])
    return pl.Series(result)


def rsi(series: pl.Series, window: int = 14) -> pl.Series:
    """Relative Strength Index."""
    delta = series.diff().to_list()
    avg_gain = [0.0] * len(delta)
    avg_loss = [0.0] * len(delta)
    for i in range(1, len(delta)):
        g = delta[i] if delta[i] > 0 else 0.0
        l = -delta[i] if delta[i] < 0 else 0.0
        if i <= window:
            avg_gain[i] = (avg_gain[i - 1] * (i - 1) + g) / i if i > 1 else g
            avg_loss[i] = (avg_loss[i - 1] * (i - 1) + l) / i if i > 1 else l
        else:
            avg_gain[i] = (avg_gain[i - 1] * (window - 1) + g) / window
            avg_loss[i] = (avg_loss[i - 1] * (window - 1) + l) / window
    rs = [avg_gain[i] / avg_loss[i] if avg_loss[i] != 0 else 100 for i in range(len(delta))]
    return pl.Series([100 - (100 / (1 + r)) for r in rs])


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
    tr = pl.Series([
        max(h - l, abs(h - c_prev), abs(l - c_prev))
        for h, l, c_prev in zip(high[1:], low[1:], close[:-1])
    ])
    result = [0.0] * len(close)
    for i in range(1, len(close)):
        tr_val = tr[i - 1] if i - 1 < len(tr) else 0.0
        result[i] = (result[i - 1] * (window - 1) + tr_val) / window if i > 0 else tr_val
    return pl.Series(result)


def obv(close: pl.Series, volume: pl.Series) -> pl.Series:
    """On-Balance Volume."""
    result = [volume[0]]
    for i in range(1, len(close)):
        if close[i] > close[i - 1]:
            result.append(result[-1] + volume[i])
        elif close[i] < close[i - 1]:
            result.append(result[-1] - volume[i])
        else:
            result.append(result[-1])
    return pl.Series(result)


def vwap(high: pl.Series, low: pl.Series, close: pl.Series, volume: pl.Series) -> pl.Series:
    """Volume-Weighted Average Price."""
    typical = (high + low + close) / 3
    cum_pv = (typical * volume).cum_sum()
    cum_v = volume.cum_sum()
    return cum_pv / cum_v


def macd(series: pl.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, pl.Series]:
    """MACD line, signal line, histogram."""
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return {"macd": macd_line, "signal": signal_line, "histogram": histogram}
