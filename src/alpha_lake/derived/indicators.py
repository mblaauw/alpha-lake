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
    avg_gain = gain.rolling_mean(window_size=window)
    avg_loss = loss.rolling_mean(window_size=window)
    rs = avg_gain / avg_loss
    rs = rs.fill_nan(100.0).fill_null(100.0)
    rs = rs.map_elements(lambda x: 100.0 if x == float("inf") else x, return_dtype=pl.Float64)
    return 100 - (100 / (1 + rs))


def bollinger_bands(
    series: pl.Series,
    window: int = 20,
    num_std: float = 2.0,
) -> dict[str, pl.Series]:
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
    tr = (
        pl.DataFrame(
            {
                "h_l": high - low,
                "h_c": (high - close.shift(1)).abs(),
                "l_c": (low - close.shift(1)).abs(),
            }
        )
        .select(pl.max_horizontal("h_l", "h_c", "l_c"))
        .to_series()
    )
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


def macd(
    series: pl.Series, fast: int = 12, slow: int = 26, ema_window: int = 9
) -> dict[str, pl.Series]:
    """MACD line, MACD EMA, histogram."""
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    macd_ema = ema(macd_line, ema_window)
    histogram = macd_line - macd_ema
    return {"macd": macd_line, "macd_ema": macd_ema, "histogram": histogram}


# --- Phase 2.1 — Extended indicator panel ---


def returns(close: pl.Series, window: int) -> pl.Series:
    """N-day return as a decimal fraction: (close / close.shift(N)) - 1."""
    return (close / close.shift(window)) - 1


def distance_to_ma(close: pl.Series, ma: pl.Series) -> pl.Series:
    """Distance from close to moving average as a decimal: (close / ma) - 1."""
    return (close / ma) - 1


def above_ma(close: pl.Series, ma: pl.Series) -> pl.Series:
    """Boolean: close is above the moving average."""
    return close > ma


def atr_pct(atr_series: pl.Series, close: pl.Series) -> pl.Series:
    """ATR as a percentage of close: ATR / close * 100."""
    return (atr_series / close) * 100


def realized_vol(close: pl.Series, window: int, periods_per_year: int = 252) -> pl.Series:
    """Annualized realized volatility from log returns."""
    log_ret = close.log().diff()
    return log_ret.rolling_std(window_size=window) * (periods_per_year**0.5)


def relative_volume(volume: pl.Series, window: int = 20) -> pl.Series:
    """Relative volume: volume / rolling_mean(volume, window)."""
    return volume / volume.rolling_mean(window_size=window)


def dollar_volume(close: pl.Series, volume: pl.Series) -> pl.Series:
    """Dollar volume: close * volume."""
    return close * volume


def avg_dollar_volume(close: pl.Series, volume: pl.Series, window: int = 20) -> pl.Series:
    """Rolling average dollar volume."""
    dv = close * volume
    return dv.rolling_mean(window_size=window)


def pct_off_high(close: pl.Series, high: pl.Series, window: int = 252) -> pl.Series:
    """Percentage below the rolling maximum high: (close / rolling_max(high)) - 1."""
    return (close / high.rolling_max(window_size=window)) - 1


def pct_off_low(close: pl.Series, low: pl.Series, window: int = 252) -> pl.Series:
    """Percentage above the rolling minimum low: (close / rolling_min(low)) - 1."""
    return (close / low.rolling_min(window_size=window)) - 1


def is_new_high(high: pl.Series, window: int = 252) -> pl.Series:
    """Boolean: high equals the rolling maximum high over the window."""
    return high == high.rolling_max(window_size=window)


def is_new_low(low: pl.Series, window: int = 252) -> pl.Series:
    """Boolean: low equals the rolling minimum low over the window."""
    return low == low.rolling_min(window_size=window)


def gap_pct(open_: pl.Series, close: pl.Series) -> pl.Series:
    """Overnight gap as a decimal: (open / prev_close) - 1."""
    return (open_ / close.shift(1)) - 1


# --- Phase 2.2 — Momentum & Oscillator indicators ---


def adx(
    high: pl.Series, low: pl.Series, close: pl.Series, window: int = 14
) -> dict[str, pl.Series]:
    """Average Directional Index, +DI, -DI."""
    tr = _true_range(high, low, close)
    up_move = high.diff()
    down_move = -low.diff()
    pos_dm = up_move * (up_move > down_move).cast(pl.Float64) * (up_move > 0).cast(pl.Float64)
    neg_dm = down_move * (down_move > up_move).cast(pl.Float64) * (down_move > 0).cast(pl.Float64)
    atr_ = tr.rolling_mean(window_size=window)
    di_plus = 100.0 * pos_dm.rolling_mean(window_size=window) / atr_
    di_minus = 100.0 * neg_dm.rolling_mean(window_size=window) / atr_
    dx = 100.0 * (di_plus - di_minus).abs() / (di_plus + di_minus)
    dx = dx.fill_nan(0.0).fill_null(0.0)
    adx_series = dx.ewm_mean(alpha=2.0 / (window + 1), adjust=False)
    return {"adx": adx_series, "di_plus": di_plus, "di_minus": di_minus}


def aroon(high: pl.Series, low: pl.Series, window: int = 25) -> dict[str, pl.Series]:
    """Aroon Up, Aroon Down, Aroon Oscillator."""
    up = _aroon_side(high, window)
    down = _aroon_side(-low, window)
    return {"up": up, "down": down, "oscillator": up - down}


def _aroon_side(series: pl.Series, window: int) -> pl.Series:
    """Helper: Aroon calculation for one direction."""
    vals = _aroon_impl(series, window)
    return pl.Series(vals)


def _aroon_impl(series: pl.Series, window: int) -> list[float | None]:
    out: list[float | None] = []
    for i in range(len(series)):
        start = max(0, i - window + 1)
        w = series[start : i + 1]
        if len(w) < window:
            out.append(None)
        else:
            max_idx_val = w.arg_max()
            max_idx = int(max_idx_val) if max_idx_val is not None else 0
            periods_since = len(w) - 1 - max_idx
            val: float | None = 100.0 * (window - periods_since) / window
            out.append(val)
    return out


def choppiness_index(
    high: pl.Series, low: pl.Series, close: pl.Series, window: int = 14
) -> pl.Series:
    """Choppiness Index — trending vs ranging."""
    import math

    log_n = math.log10(window)
    tr = _true_range(high, low, close)
    tr_sum = tr.rolling_mean(window_size=window) * window
    hh = high.rolling_max(window_size=window)
    ll = low.rolling_min(window_size=window)
    ratio = tr_sum / (hh - ll)
    ratio = ratio.fill_nan(1.0).fill_null(1.0)
    return 100.0 * ratio.log10() / log_n


def ppo(series: pl.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, pl.Series]:
    """Percentage Price Oscillator."""
    ema_fast = series.ewm_mean(alpha=2.0 / (fast + 1), adjust=False)
    ema_slow = series.ewm_mean(alpha=2.0 / (slow + 1), adjust=False)
    ppo_line = (ema_fast - ema_slow) / ema_slow * 100.0
    sig = ppo_line.ewm_mean(alpha=2.0 / (signal + 1), adjust=False)
    return {"ppo": ppo_line, "signal": sig, "histogram": ppo_line - sig}


def roc(series: pl.Series, window: int = 12) -> pl.Series:
    """Rate of Change as percentage: ((close / close(N)) - 1) * 100."""
    return (series / series.shift(window) - 1.0) * 100.0


def trix(series: pl.Series, window: int = 15) -> pl.Series:
    """Triple-Smoothed Exponential Average rate of change."""
    alpha = 2.0 / (window + 1)
    s1 = series.ewm_mean(alpha=alpha, adjust=False)
    s2 = s1.ewm_mean(alpha=alpha, adjust=False)
    s3 = s2.ewm_mean(alpha=alpha, adjust=False)
    return (s3 / s3.shift(1) - 1.0) * 100.0


def stochastic(
    high: pl.Series, low: pl.Series, close: pl.Series, k_window: int = 14, d_window: int = 3
) -> dict[str, pl.Series]:
    """Stochastic Oscillator %K and %D."""
    hh = high.rolling_max(window_size=k_window)
    ll = low.rolling_min(window_size=k_window)
    k = 100.0 * (close - ll) / (hh - ll)
    k = k.fill_nan(50.0).fill_null(50.0)
    d = k.rolling_mean(window_size=d_window)
    return {"k": k, "d": d}


def stochastic_rsi(series: pl.Series, window: int = 14) -> pl.Series:
    """Stochastic RSI."""
    rsi_vals = rsi(series, window)
    ll = rsi_vals.rolling_min(window_size=window)
    hh = rsi_vals.rolling_max(window_size=window)
    out = (rsi_vals - ll) / (hh - ll)
    return out.fill_nan(0.5).fill_null(0.5)


def williams_r(high: pl.Series, low: pl.Series, close: pl.Series, window: int = 14) -> pl.Series:
    """Williams %R."""
    hh = high.rolling_max(window_size=window)
    ll = low.rolling_min(window_size=window)
    return -100.0 * (hh - close) / (hh - ll)


def cci(high: pl.Series, low: pl.Series, close: pl.Series, window: int = 20) -> pl.Series:
    """Commodity Channel Index."""
    tp = (high + low + close) / 3.0
    ma = tp.rolling_mean(window_size=window)
    mad = (tp - ma).abs().rolling_mean(window_size=window)
    mad = mad.fill_nan(1.0).fill_null(1.0)
    return (tp - ma) / (0.015 * mad)


def tsi(series: pl.Series, long: int = 25, short: int = 13) -> pl.Series:
    """True Strength Index."""
    m = series.diff()
    abs_m = m.abs()
    alpha_l = 2.0 / (long + 1)
    alpha_s = 2.0 / (short + 1)
    smoothed_m = m.ewm_mean(alpha=alpha_l, adjust=False).ewm_mean(alpha=alpha_s, adjust=False)
    smoothed_abs = abs_m.ewm_mean(alpha=alpha_l, adjust=False).ewm_mean(alpha=alpha_s, adjust=False)
    smoothed_abs = smoothed_abs.fill_nan(1.0).fill_null(1.0)
    return 100.0 * smoothed_m / smoothed_abs


def ultimate_oscillator(
    high: pl.Series,
    low: pl.Series,
    close: pl.Series,
    s: int = 7,
    m: int = 14,
    long_window: int = 28,
) -> pl.Series:
    """Ultimate Oscillator — element-wise Python for type correctness."""
    cl = close.to_list()
    lw = low.to_list()
    pc = close.shift(1).to_list()
    tr = _true_range(high, low, close)
    tr_l = tr.to_list()
    n = len(cl)
    uo_vals: list[float | None] = []
    for i in range(n):
        ss = max(0, i - s + 1)
        ms = max(0, i - m + 1)
        ls = max(0, i - long_window + 1)
        bp7 = 0.0
        bp14 = 0.0
        bp28 = 0.0
        tr7 = 0.0
        tr14 = 0.0
        tr28 = 0.0
        for j in range(ss, i + 1):
            tr7 += float(tr_l[j]) if tr_l[j] is not None else 0.0
            mhl = min(lw[j], pc[j]) if (lw[j] is not None and pc[j] is not None) else 0.0
            bp7 += max(cl[j] - mhl, 0.0) if cl[j] is not None else 0.0
        for j in range(ms, i + 1):
            tr14 += float(tr_l[j]) if tr_l[j] is not None else 0.0
            mhl = min(lw[j], pc[j]) if (lw[j] is not None and pc[j] is not None) else 0.0
            bp14 += max(cl[j] - mhl, 0.0) if cl[j] is not None else 0.0
        for j in range(ls, i + 1):
            tr28 += float(tr_l[j]) if tr_l[j] is not None else 0.0
            mhl = min(lw[j], pc[j]) if (lw[j] is not None and pc[j] is not None) else 0.0
            bp28 += max(cl[j] - mhl, 0.0) if cl[j] is not None else 0.0
        a7 = bp7 / tr7 if tr7 else 0.5
        a14 = bp14 / tr14 if tr14 else 0.5
        a28 = bp28 / tr28 if tr28 else 0.5
        uo_vals.append(100.0 * (4.0 * a7 + 2.0 * a14 + 1.0 * a28) / 7.0)
    return pl.Series(uo_vals)


def chande_momentum(series: pl.Series, window: int = 14) -> pl.Series:
    """Chande Momentum Oscillator."""
    delta = series.diff()
    up_sum = delta * (delta > 0).cast(pl.Float64)
    down_sum = (-delta) * (delta < 0).cast(pl.Float64)
    su = up_sum.rolling_sum(window_size=window)
    sd = down_sum.rolling_sum(window_size=window)
    return 100.0 * (su - sd) / (su + sd).fill_nan(1.0).fill_null(1.0)


def balance_of_power(
    open_: pl.Series, high: pl.Series, low: pl.Series, close: pl.Series
) -> pl.Series:
    """Balance of Power: (close - open) / (high - low)."""
    return (close - open_) / (high - low).fill_nan(1.0).fill_null(1.0)


# --- Phase 2.3 — Volume & Money Flow indicators ---


def ad_line(high: pl.Series, low: pl.Series, close: pl.Series, volume: pl.Series) -> pl.Series:
    """Accumulation / Distribution Line."""
    clv = ((close - low) - (high - close)) / (high - low).fill_nan(1.0).fill_null(1.0)
    mfv = volume.cast(pl.Float64) * clv
    return mfv.cum_sum()


def cmf(
    high: pl.Series, low: pl.Series, close: pl.Series, volume: pl.Series, window: int = 20
) -> pl.Series:
    """Chaikin Money Flow."""
    clv = ((close - low) - (high - close)) / (high - low).fill_nan(1.0).fill_null(1.0)
    mfv = volume.cast(pl.Float64) * clv
    mfv_sum = mfv.rolling_sum(window_size=window)
    vol_sum = volume.cast(pl.Float64).rolling_sum(window_size=window)
    return mfv_sum / vol_sum


def chaikin_oscillator(
    high: pl.Series, low: pl.Series, close: pl.Series, volume: pl.Series
) -> pl.Series:
    """Chaikin Oscillator: EMA(A/D, 3) - EMA(A/D, 10)."""
    ad = ad_line(high, low, close, volume)
    fast = ad.ewm_mean(alpha=2.0 / 4, adjust=False)
    slow = ad.ewm_mean(alpha=2.0 / 11, adjust=False)
    return fast - slow


def mfi(
    high: pl.Series, low: pl.Series, close: pl.Series, volume: pl.Series, window: int = 14
) -> pl.Series:
    """Money Flow Index."""
    typical = (high + low + close) / 3.0
    money_flow = typical * volume.cast(pl.Float64)
    up = typical > typical.shift(1)
    pos_mf = (money_flow * up.cast(pl.Float64)).rolling_sum(window_size=window)
    neg_mf = (money_flow * (~up).cast(pl.Float64)).rolling_sum(window_size=window)
    neg_mf = neg_mf.fill_nan(1.0).fill_null(1.0)
    mfr = pos_mf / neg_mf
    return 100.0 - (100.0 / (1.0 + mfr))


def vpt(close: pl.Series, volume: pl.Series) -> pl.Series:
    """Volume Price Trend."""
    pct = (close - close.shift(1)) / close.shift(1)
    return (pct * volume.cast(pl.Float64)).cum_sum()


def force_index(close: pl.Series, volume: pl.Series, window: int = 13) -> pl.Series:
    """Force Index: EMA(volume x (close - close_prev), window)."""
    raw = volume.cast(pl.Float64) * (close - close.shift(1))
    return raw.ewm_mean(alpha=2.0 / (window + 1), adjust=False)


def eom(high: pl.Series, low: pl.Series, volume: pl.Series, window: int = 14) -> pl.Series:
    """Ease of Movement."""
    midpoint = (high + low) / 2.0
    box_ratio = (volume.cast(pl.Float64) / 10000.0).fill_nan(1.0).fill_null(1.0)
    raw = (midpoint - midpoint.shift(1)) / box_ratio
    return raw.ewm_mean(alpha=2.0 / (window + 1), adjust=False)


def obv_slope(close: pl.Series, volume: pl.Series, window: int = 20) -> pl.Series:
    """OBV slope over N periods (simple linear regression slope)."""
    return _linreg_slope(obv(close, volume), window)


def volume_spike(
    volume: pl.Series, rvol_threshold: float = 2.5, rvol_series: pl.Series | None = None
) -> pl.Series:
    """Boolean: True when relative volume exceeds threshold OR volume exceeds avg + 2.5 sigma."""
    rv = rvol_series if rvol_series is not None else relative_volume(volume, 20)
    vol_mean = volume.rolling_mean(window_size=20)
    vol_std = volume.rolling_std(window_size=20).fill_nan(1.0).fill_null(1.0)
    return (rv > rvol_threshold) | (volume > vol_mean + 2.5 * vol_std)


# --- Phase 2.4 — Volatility & Structure indicators ---


def keltner_channels(
    high: pl.Series,
    low: pl.Series,
    close: pl.Series,
    ma_window: int = 20,
    atr_window: int = 10,
    multiplier: float = 2.0,
) -> dict[str, pl.Series]:
    """Keltner Channels: middle (EMA), upper, lower."""
    mid = close.ewm_mean(alpha=2.0 / (ma_window + 1), adjust=False)
    atr_ = _true_range(high, low, close).rolling_mean(window_size=atr_window)
    return {"middle": mid, "upper": mid + multiplier * atr_, "lower": mid - multiplier * atr_}


def donchian_channels(high: pl.Series, low: pl.Series, window: int = 20) -> dict[str, pl.Series]:
    """Donchian Channels: upper (highest high), lower (lowest low), middle."""
    upper = high.rolling_max(window_size=window)
    lower = low.rolling_min(window_size=window)
    return {"upper": upper, "lower": lower, "middle": (upper + lower) / 2.0}


def percent_b(close: pl.Series, bb_upper: pl.Series, bb_lower: pl.Series) -> pl.Series:
    """%B: position within Bollinger Bands."""
    denom = bb_upper - bb_lower
    return (close - bb_lower) / denom


def bandwidth(bb_upper: pl.Series, bb_lower: pl.Series, bb_middle: pl.Series) -> pl.Series:
    """Bandwidth: (upper - lower) / middle."""
    return (bb_upper - bb_lower) / bb_middle


def bollinger_squeeze(bandwidth_series: pl.Series, window: int = 126) -> pl.Series:
    """Bollinger Squeeze: True when Bandwidth at N-period minimum."""
    min_bw = bandwidth_series.rolling_min(window_size=window)
    return bandwidth_series == min_bw


def range_expansion(
    high: pl.Series, low: pl.Series, close: pl.Series, window: int = 14
) -> pl.Series:
    """Range Expansion / Contraction: current TR / ATR."""
    tr = _true_range(high, low, close)
    atr_ = tr.rolling_mean(window_size=window).fill_nan(1.0).fill_null(1.0)
    return tr / atr_


def true_range(high: pl.Series, low: pl.Series, close: pl.Series) -> pl.Series:
    """True Range."""
    return _true_range(high, low, close)


def rolling_std(series: pl.Series, window: int = 20) -> pl.Series:
    """Rolling standard deviation."""
    return series.rolling_std(window_size=window)


def wma(series: pl.Series, window: int = 20) -> pl.Series:
    """Weighted Moving Average — linear weights."""
    n = float(window)
    w_sum = n * (n + 1.0) / 2.0
    out: list[float | None] = []
    for i in range(len(series)):
        if i < window - 1:
            out.append(None)
        else:
            vals: list[float] = []
            all_ok = True
            for j in range(i - window + 1, i + 1):
                v = series[j]
                if v is None:
                    all_ok = False
                    break
                vals.append(float(v))
            if not all_ok:
                out.append(None)
            else:
                weighted = sum((j + 1.0) * vals[j] for j in range(window)) / w_sum
                out.append(weighted)
    return pl.Series(out)


def kama(series: pl.Series, er_window: int = 10, fast_sc: int = 2, slow_sc: int = 30) -> pl.Series:
    """Kaufman Adaptive Moving Average."""
    s = series.to_list()
    n = len(s)
    fast = 2.0 / (fast_sc + 1.0)
    slow = 2.0 / (slow_sc + 1.0)
    vals: list[float | None] = [None] * n
    for i in range(er_window, n):
        ci = s[i]
        ci_er = s[i - er_window]
        if ci is None or ci_er is None:
            vals[i] = vals[i - 1] if vals[i - 1] is not None else None
            continue
        change = abs(ci - ci_er)
        if change == 0:
            er = 0.0
        else:
            volatility = 0.0
            for j in range(i - er_window + 1, i + 1):
                cj = s[j]
                cjm1 = s[j - 1]
                if cj is not None and cjm1 is not None:
                    volatility += abs(cj - cjm1)
            er = change / volatility if volatility else 0.0
        sc = (er * (fast - slow) + slow) ** 2
        prev = vals[i - 1] if vals[i - 1] is not None else ci_er
        vals[i] = prev + sc * (ci - prev)
    return pl.Series(vals)


def linear_regression_slope(series: pl.Series, window: int = 20) -> pl.Series:
    """Linear regression slope over N periods."""
    return _linreg_slope(series, window)


def _linreg_slope(series: pl.Series, window: int) -> pl.Series:
    """Helper: linear regression slope over rolling window."""
    n = float(window)
    x_mean = (window - 1.0) / 2.0
    x_ss = sum((i - x_mean) ** 2 for i in range(window))
    out: list[float | None] = []
    for i in range(len(series)):
        if i < window - 1:
            out.append(None)
        else:
            y = [
                float(series[j]) if series[j] is not None else 0.0
                for j in range(i - window + 1, i + 1)
            ]
            y_m = sum(y) / n
            slope = sum((j - x_mean) * (y[j] - y_m) for j in range(window)) / x_ss
            out.append(slope)
    return pl.Series(out)


def linear_regression_channel(
    series: pl.Series, window: int = 20, num_std: float = 2.0
) -> dict[str, pl.Series]:
    """Linear regression channel: middle (linreg), upper, lower."""
    n = float(window)
    x_m = (window - 1.0) / 2.0
    x_ss = sum((i - x_m) ** 2 for i in range(window))
    middle_vals: list[float | None] = []
    upper_vals: list[float | None] = []
    lower_vals: list[float | None] = []
    for i in range(len(series)):
        if i < window - 1:
            middle_vals.append(None)
            upper_vals.append(None)
            lower_vals.append(None)
        else:
            raw = [series[j] for j in range(i - window + 1, i + 1)]
            if any(v is None for v in raw):
                middle_vals.append(None)
                upper_vals.append(None)
                lower_vals.append(None)
            else:
                y_f = [float(v) for v in raw]  # type: ignore[misc]
                y_m = sum(y_f) / n
                slope = sum((j - x_m) * (y_f[j] - y_m) for j in range(window)) / x_ss
                intercept = y_m - slope * x_m
                m = intercept + slope * (window - 1) / 2.0
                resid = [y_f[j] - (intercept + slope * j) for j in range(window)]
                se = (sum(r**2 for r in resid) / (window - 2)) ** 0.5 if window > 2 else 0.0
                middle_vals.append(m)
                upper_vals.append(m + num_std * se if se else m)
                lower_vals.append(m - num_std * se if se else m)
    return {
        "middle": pl.Series(middle_vals),
        "upper": pl.Series(upper_vals),
        "lower": pl.Series(lower_vals),
    }


def pivot_points(
    high: pl.Series, low: pl.Series, left: int = 5, right: int = 5
) -> dict[str, pl.Series]:
    """Pivot high / low detection."""
    n = len(high)
    pivots_h: list[float | None] = [None] * n
    pivots_l: list[float | None] = [None] * n
    for i in range(left, n - right):
        h_vals: list[float] = []
        l_vals: list[float] = []
        valid = True
        for j in range(i - left, i + right + 1):
            hv = high[j]
            lv = low[j]
            if hv is None or lv is None:
                valid = False
                break
            h_vals.append(float(hv))
            l_vals.append(float(lv))
        if not valid:
            continue
        h_mid = h_vals[left]
        l_mid = l_vals[left]
        if h_mid == max(h_vals):
            pivots_h[i] = h_mid
        if l_mid == min(l_vals):
            pivots_l[i] = l_mid
    return {"high": pl.Series(pivots_h), "low": pl.Series(pivots_l)}


def inside_bar(high: pl.Series, low: pl.Series) -> pl.Series:
    """Inside Bar: current bar entirely inside prior bar's range."""
    prev_high = high.shift(1)
    prev_low = low.shift(1)
    return (high <= prev_high) & (low >= prev_low)


def outside_bar(high: pl.Series, low: pl.Series) -> pl.Series:
    """Outside Bar: current bar engulfs prior bar's range."""
    prev_high = high.shift(1)
    prev_low = low.shift(1)
    return (high > prev_high) & (low < prev_low)


def gap_fill(
    high: pl.Series, low: pl.Series, open_: pl.Series, close: pl.Series, lookback: int = 5
) -> pl.Series:
    """Gap Fill Detection: True if price retraces to close the gap within N periods."""
    prev_close = close.shift(1).to_list()
    hi = high.to_list()
    lo = low.to_list()
    n = len(high)
    result: list[bool | None] = [None] * n
    for i in range(1, n):
        pc = prev_close[i]
        if pc is None:
            result[i] = None
            continue
        gap_top = max(open_[i], pc)
        gap_bot = min(open_[i], pc)
        for j in range(i + 1, min(i + lookback + 1, n)):
            if lo[j] is not None and lo[j] <= gap_top and hi[j] is not None and hi[j] >= gap_bot:
                result[i] = True
                break
        if result[i] is None:
            result[i] = False
    return pl.Series(result)


# --- Phase 2.5 — Relative Performance indicators (require SPY bars) ---


def compute_beta(
    symbol_returns: pl.Series, benchmark_returns: pl.Series, window: int = 20
) -> pl.Series:
    """Rolling beta vs a benchmark over *window* periods."""
    out: list[float | None] = []
    n = len(symbol_returns)
    for i in range(n):
        if i < window:
            out.append(None)
        else:
            sr: list[float] = []
            br: list[float] = []
            for j in range(i - window, i):
                sv = symbol_returns[j]
                bv = benchmark_returns[j]
                if sv is None or bv is None:
                    sr.clear()
                    break
                sr.append(float(sv))
                br.append(float(bv))
            if len(sr) < window:
                out.append(None)
            else:
                s_mean = sum(sr) / window
                b_mean = sum(br) / window
                cov = sum((sr[j] - s_mean) * (br[j] - b_mean) for j in range(window))
                var_b = sum((br[j] - b_mean) ** 2 for j in range(window))
                out.append(cov / var_b if var_b else 0.0)
    return pl.Series(out)


def compute_alpha(
    symbol_returns: pl.Series,
    benchmark_returns: pl.Series,
    beta_series: pl.Series,
    risk_free_rate: float = 0.0,
) -> pl.Series:
    """Alpha vs benchmark: actual return - (RFR + beta x (benchmark_return - RFR))."""
    return symbol_returns - (risk_free_rate + beta_series * (benchmark_returns - risk_free_rate))


def compute_relative_strength(
    symbol_returns: pl.Series, benchmark_returns: pl.Series, window: int = 20
) -> pl.Series:
    """Relative strength: (1 + R_stock) / (1 + R_benchmark) - 1."""
    stock_r = symbol_returns.rolling_sum(window_size=window)
    bench_r = benchmark_returns.rolling_sum(window_size=window)
    bench_r = bench_r.fill_nan(1.0).fill_null(1.0)
    return (1.0 + stock_r) / (1.0 + bench_r) - 1.0


def compute_rolling_correlation(
    symbol_returns: pl.Series, benchmark_returns: pl.Series, window: int = 60
) -> pl.Series:
    """Rolling Pearson correlation with benchmark over *window* periods."""
    out: list[float | None] = []
    n = len(symbol_returns)
    for i in range(n):
        if i < window:
            out.append(None)
        else:
            sr: list[float] = []
            br: list[float] = []
            for j in range(i - window, i):
                sv = symbol_returns[j]
                bv = benchmark_returns[j]
                if sv is None or bv is None:
                    sr.clear()
                    break
                sr.append(float(sv))
                br.append(float(bv))
            if len(sr) < window:
                out.append(None)
            else:
                s_mean = sum(sr) / window
                b_mean = sum(br) / window
                cov = sum((sr[j] - s_mean) * (br[j] - b_mean) for j in range(window))
                std_s = (sum((sr[j] - s_mean) ** 2 for j in range(window)) / window) ** 0.5
                std_b = (sum((br[j] - b_mean) ** 2 for j in range(window)) / window) ** 0.5
                out.append(cov / (window * std_s * std_b) if std_s and std_b else None)
    return pl.Series(out)


# --- Phase 2.6 — Utility indicators ---


def log_return(close: pl.Series) -> pl.Series:
    """Log return: ln(close / close_prev)."""
    return close.log() - close.shift(1).log()


def ma_stack(sma_20: pl.Series, sma_50: pl.Series, sma_200: pl.Series) -> pl.Series:
    """MA stack alignment.

    Returns 1 (aligned up: 20 > 50 > 200), -1 (aligned down: 20 < 50 < 200),
    or 0 (mixed/transitional).
    """
    aligned_up = (sma_20 > sma_50) & (sma_50 > sma_200)
    aligned_down = (sma_20 < sma_50) & (sma_50 < sma_200)
    return aligned_up.cast(pl.Int8) - aligned_down.cast(pl.Int8)


def ma_slope(ma_series: pl.Series, window: int = 5) -> pl.Series:
    """Slope of a moving average over *window* periods (rate of change)."""
    return (ma_series - ma_series.shift(window)) / window


def rsi_divergence(close: pl.Series, rsi_series: pl.Series, window: int = 14) -> pl.Series:
    """Detect RSI divergence.

    Looks for price making a lower low while RSI makes a higher low (positive
    divergence) or price making a higher high while RSI makes a lower high
    (negative divergence).

    Returns 1 (positive), -1 (negative), or 0 (none).
    """
    out: list[int | None] = [None] * len(close)
    periods = max(5, window // 3)
    for i in range(periods * 2, len(close)):
        left = i - periods
        right = i + 1
        p_slice = close[left:right].to_list()
        r_slice = rsi_series[left:right].to_list()
        p_min = min((v for v in p_slice if v is not None), default=None)
        p_max = max((v for v in p_slice if v is not None), default=None)
        r_min = min((v for v in r_slice if v is not None), default=None)
        r_max = max((v for v in r_slice if v is not None), default=None)
        if p_min is None or r_min is None or p_max is None or r_max is None:
            out[i] = 0
            continue
        p_min_idx = p_slice.index(p_min)
        r_min_idx = r_slice.index(r_min)
        p_max_idx = p_slice.index(p_max)
        r_max_idx = r_slice.index(r_max)
        positive_div = p_min_idx > r_min_idx and r_min > p_min
        negative_div = p_max_idx > r_max_idx and r_max < p_max
        if positive_div:
            out[i] = 1
        elif negative_div:
            out[i] = -1
        else:
            out[i] = 0
    return pl.Series(out)


def _true_range(high: pl.Series, low: pl.Series, close: pl.Series) -> pl.Series:
    """True Range (shared helper for ADX and Choppiness)."""
    h_l = high - low
    h_c = (high - close.shift(1)).abs()
    l_c = (low - close.shift(1)).abs()
    return (
        pl.DataFrame({"a": h_l, "b": h_c, "c": l_c})
        .select(pl.max_horizontal("a", "b", "c"))
        .to_series()
    )
