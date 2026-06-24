from __future__ import annotations

from datetime import datetime
from typing import Any

import polars as pl

from alpha_lake.canonical import compute_version_hash
from alpha_lake.derived.indicators import (
    above_ma,
    ad_line,
    adx,
    aroon,
    atr,
    atr_pct,
    avg_dollar_volume,
    balance_of_power,
    bandwidth,
    bollinger_squeeze,
    cci,
    chaikin_oscillator,
    chande_momentum,
    choppiness_index,
    cmf,
    compute_alpha,
    compute_beta,
    compute_relative_strength,
    compute_rolling_correlation,
    distance_to_ma,
    dollar_volume,
    donchian_channels,
    ema,
    eom,
    force_index,
    gap_fill,
    gap_pct,
    inside_bar,
    is_new_high,
    is_new_low,
    kama,
    keltner_channels,
    linear_regression_channel,
    linear_regression_slope,
    log_return,
    ma_slope,
    ma_stack,
    macd,
    mfi,
    obv,
    obv_slope,
    outside_bar,
    pct_off_high,
    pct_off_low,
    percent_b,
    pivot_points,
    ppo,
    range_expansion,
    realized_vol,
    relative_volume,
    returns,
    roc,
    rolling_std,
    rsi,
    rsi_divergence,
    sma,
    stochastic,
    stochastic_rsi,
    trix,
    true_range,
    tsi,
    ultimate_oscillator,
    volume_spike,
    vpt,
    vwap,
    williams_r,
    wma,
)

_TECH_SOURCE_ID = "derived"


def compute_all_indicators(
    bars: pl.DataFrame,
    as_of: datetime,
    benchmark_bars: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Compute all technical indicators from a bars DataFrame.

    ``bars`` must contain ``security_id``, ``effective_date``, ``available_at``,
    ``open``, ``high``, ``low``, ``close``, ``volume`` sorted by
    ``(security_id, effective_date)``.

    When *benchmark_bars* is provided (e.g. SPY bars), relative performance
    indicators (beta, alpha, relative strength, correlation) are also computed.

    Returns a DataFrame conforming to the ``TechnicalIndicatorFact`` schema with
    one row per ``(security_id, effective_date)``.  Null indicator values are
    left as ``None`` where there is insufficient history for the computation.
    """

    def _v(s: pl.Series, idx: int) -> float | None:
        v = s[idx]
        return float(v) if v is not None else None

    def _b(s: pl.Series, idx: int) -> bool | None:
        v = s[idx]
        return bool(v) if v is not None else None

    bars = bars.filter(pl.col("available_at") <= as_of)
    _spy_returns_map: dict[str, float] | None = None
    if benchmark_bars is not None and not benchmark_bars.is_empty():
        bm = benchmark_bars.sort("effective_date")
        bm_closes = bm["close"]
        bm_returns = bm_closes.diff() / bm_closes.shift(1)
        bm_dates = [str(d) for d in bm["effective_date"]]
        _spy_returns_map = {}
        for i, d in enumerate(bm_dates):
            r = bm_returns[i]
            if r is not None:
                _spy_returns_map[d] = float(r)
    rows: list[dict[str, Any]] = []

    for sid in bars["security_id"].unique():
        sym_bars = bars.filter(pl.col("security_id") == sid).sort("effective_date")
        close = sym_bars["close"]
        high = sym_bars["high"]
        low = sym_bars["low"]
        open_ = sym_bars["open"]
        volume = sym_bars["volume"]
        src_avail = sym_bars["available_at"].max()
        if src_avail is None:
            continue

        # Core trend
        _sma20 = sma(close, 20)
        _sma50 = sma(close, 50)
        _sma200 = sma(close, 200)
        _ema12 = ema(close, 12)
        _ema26 = ema(close, 26)

        # Oscillator
        _rsi14 = rsi(close, 14)

        # ATR
        _atr14 = atr(high, low, close, 14)

        # OBV
        _obv = obv(close, volume)

        # VWAP
        _vwap = vwap(high, low, close, volume)

        # MACD
        _macd = macd(close, 12, 26, 9)

        # Returns
        _ret1 = returns(close, 1)
        _ret5 = returns(close, 5)
        _ret21 = returns(close, 21)
        _ret63 = returns(close, 63)
        _ret126 = returns(close, 126)
        _ret252 = returns(close, 252)

        # Volume
        _rvol = relative_volume(volume, 20)
        _dolv = dollar_volume(close, volume)
        _adol20 = avg_dollar_volume(close, volume, 20)
        _ad_line = ad_line(high, low, close, volume)
        _cmf20 = cmf(high, low, close, volume, 20)
        _chaikin = chaikin_oscillator(high, low, close, volume)
        _mfi14 = mfi(high, low, close, volume, 14)
        _vpt_val = vpt(close, volume)
        _force13 = force_index(close, volume, 13)
        _eom14 = eom(high, low, volume, 14)
        _obv_slope20 = obv_slope(close, volume, 20)
        _vol_spike = volume_spike(volume, 2.5, _rvol)

        # Price action
        _gap = gap_pct(open_, close)
        _p52h = pct_off_high(close, high, 252)
        _p52l = pct_off_low(close, low, 252)
        _n52h = is_new_high(high, 252)
        _n52l = is_new_low(low, 252)

        # Distance to MA
        _dma20 = distance_to_ma(close, _sma20)
        _dma50 = distance_to_ma(close, _sma50)
        _dma200 = distance_to_ma(close, _sma200)

        # Above MA
        _ama20 = above_ma(close, _sma20)
        _ama50 = above_ma(close, _sma50)
        _ama200 = above_ma(close, _sma200)

        # ATR%
        _atr_pct = atr_pct(_atr14, close)

        # Realized vol
        _rv21 = realized_vol(close, 21)
        _rv63 = realized_vol(close, 63)

        # Bollinger fields (reused by %B, Bandwidth)
        _bb_result = _bollinger_fields(close)
        _pct_b = percent_b(close, _bb_result["upper"], _bb_result["lower"])
        _bw = bandwidth(_bb_result["upper"], _bb_result["lower"], _bb_result["middle"])
        _bb_squeeze = bollinger_squeeze(_bw, 126)

        # Volatility & Structure
        _keltner = keltner_channels(high, low, close, 20, 10, 2.0)
        _donch = donchian_channels(high, low, 20)
        _range_exp = range_expansion(high, low, close, 14)
        _tr = true_range(high, low, close)
        _std20 = rolling_std(close, 20)
        _wma20 = wma(close, 20)
        _kama10 = kama(close, 10, 2, 30)
        _linreg_slope = linear_regression_slope(close, 20)
        _linreg_ch = linear_regression_channel(close, 20, 2.0)
        _pivots = pivot_points(high, low, 5, 5)
        _inside = inside_bar(high, low)
        _outside = outside_bar(high, low)
        _gap_fill = gap_fill(high, low, open_, close, 5)

        # Utility
        _log_ret = log_return(close)
        _ma_stack = ma_stack(_sma20, _sma50, _sma200)
        _ma_slope20 = ma_slope(_sma20, 5)
        _ma_slope50 = ma_slope(_sma50, 5)
        _ma_slope200 = ma_slope(_sma200, 5)
        _rsi_div = rsi_divergence(close, _rsi14, 14)

        # Momentum & Oscillator
        _adx = adx(high, low, close, 14)
        _aroon = aroon(high, low, 25)
        _chop = choppiness_index(high, low, close, 14)
        _ppo = ppo(close, 12, 26, 9)
        _roc12 = roc(close, 12)
        _trix15 = trix(close, 15)
        _stoch = stochastic(high, low, close, 14, 3)
        _stoch_rsi = stochastic_rsi(close, 14)
        _wr = williams_r(high, low, close, 14)
        _cci = cci(high, low, close, 20)
        _tsi = tsi(close, 25, 13)
        _uo = ultimate_oscillator(high, low, close, 7, 14, 28)
        _cmo = chande_momentum(close, 14)
        _bop = balance_of_power(open_, high, low, close)

        # Relative Performance (requires SPY)
        if _spy_returns_map is not None:
            sym_dates = [str(d) for d in sym_bars["effective_date"]]
            align_rets = [_spy_returns_map.get(d, 0.0) for d in sym_dates]
            _spy_series = pl.Series(align_rets)
            _daily_rets = close.diff() / close.shift(1)
            _beta20 = compute_beta(_daily_rets, _spy_series, 20)
            _beta60 = compute_beta(_daily_rets, _spy_series, 60)
            _alpha = compute_alpha(_daily_rets, _spy_series, _beta20)
            _rs20 = compute_relative_strength(_daily_rets, _spy_series, 20)
            _rs60 = compute_relative_strength(_daily_rets, _spy_series, 60)
            _corr = compute_rolling_correlation(_daily_rets, _spy_series, 60)
        else:
            _beta20 = _beta60 = _alpha = _rs20 = _rs60 = _corr = pl.Series([None] * len(sym_bars))

        for i in range(len(sym_bars)):
            rows.append(
                {
                    "security_id": sid,
                    "effective_date": sym_bars["effective_date"][i],
                    "available_at": as_of,
                    "source_id": _TECH_SOURCE_ID,
                    "sma_20": _v(_sma20, i),
                    "sma_50": _v(_sma50, i),
                    "sma_200": _v(_sma200, i),
                    "ema_12": _v(_ema12, i),
                    "ema_26": _v(_ema26, i),
                    "rsi_14": _v(_rsi14, i),
                    "bb_upper": _v(_bb_result["upper"], i),
                    "bb_middle": _v(_bb_result["middle"], i),
                    "bb_lower": _v(_bb_result["lower"], i),
                    "atr_14": _v(_atr14, i),
                    "obv": _v(_obv, i),
                    "vwap": _v(_vwap, i),
                    "macd": _v(_macd["macd"], i),
                    "macd_ema": _v(_macd["macd_ema"], i),
                    "macd_histogram": _v(_macd["histogram"], i),
                    "return_1": _v(_ret1, i),
                    "return_5": _v(_ret5, i),
                    "return_21": _v(_ret21, i),
                    "return_63": _v(_ret63, i),
                    "return_126": _v(_ret126, i),
                    "return_252": _v(_ret252, i),
                    "dist_to_ma_20": _v(_dma20, i),
                    "dist_to_ma_50": _v(_dma50, i),
                    "dist_to_ma_200": _v(_dma200, i),
                    "above_ma_20": _b(_ama20, i),
                    "above_ma_50": _b(_ama50, i),
                    "above_ma_200": _b(_ama200, i),
                    "atr_pct": _v(_atr_pct, i),
                    "realized_vol_21": _v(_rv21, i),
                    "realized_vol_63": _v(_rv63, i),
                    "rvol": _v(_rvol, i),
                    "dollar_volume": _v(_dolv, i),
                    "avg_dollar_volume_20": _v(_adol20, i),
                    "keltner_upper": _v(_keltner["upper"], i),
                    "keltner_middle": _v(_keltner["middle"], i),
                    "keltner_lower": _v(_keltner["lower"], i),
                    "donchian_upper": _v(_donch["upper"], i),
                    "donchian_middle": _v(_donch["middle"], i),
                    "donchian_lower": _v(_donch["lower"], i),
                    "percent_b": _v(_pct_b, i),
                    "bandwidth": _v(_bw, i),
                    "bb_squeeze": _b(_bb_squeeze, i),
                    "range_expansion": _v(_range_exp, i),
                    "true_range": _v(_tr, i),
                    "rolling_std_20": _v(_std20, i),
                    "wma_20": _v(_wma20, i),
                    "kama_10": _v(_kama10, i),
                    "linreg_slope_20": _v(_linreg_slope, i),
                    "linreg_channel_upper": _v(_linreg_ch["upper"], i),
                    "linreg_channel_middle": _v(_linreg_ch["middle"], i),
                    "linreg_channel_lower": _v(_linreg_ch["lower"], i),
                    "pivot_high": _v(_pivots["high"], i),
                    "pivot_low": _v(_pivots["low"], i),
                    "inside_bar": _b(_inside, i),
                    "outside_bar": _b(_outside, i),
                    "gap_fill": _b(_gap_fill, i),
                    "beta_20d": _v(_beta20, i),
                    "beta_60d": _v(_beta60, i),
                    "alpha": _v(_alpha, i),
                    "rs_spy_20d": _v(_rs20, i),
                    "rs_spy_60d": _v(_rs60, i),
                    "corr_spy": _v(_corr, i),
                    "ad_line": _v(_ad_line, i),
                    "cmf_20": _v(_cmf20, i),
                    "chaikin_osc": _v(_chaikin, i),
                    "mfi_14": _v(_mfi14, i),
                    "vpt": _v(_vpt_val, i),
                    "force_index_13": _v(_force13, i),
                    "eom_14": _v(_eom14, i),
                    "obv_slope_20": _v(_obv_slope20, i),
                    "volume_spike": _b(_vol_spike, i),
                    "pct_off_52w_high": _v(_p52h, i),
                    "pct_off_52w_low": _v(_p52l, i),
                    "is_new_52w_high": _b(_n52h, i),
                    "is_new_52w_low": _b(_n52l, i),
                    "gap_pct": _v(_gap, i),
                    "log_return": _v(_log_ret, i),
                    "ma_stack": _v(_ma_stack, i),
                    "ma_slope_20": _v(_ma_slope20, i),
                    "ma_slope_50": _v(_ma_slope50, i),
                    "ma_slope_200": _v(_ma_slope200, i),
                    "rsi_divergence": _v(_rsi_div, i),
                    "adx_14": _v(_adx["adx"], i),
                    "di_plus_14": _v(_adx["di_plus"], i),
                    "di_minus_14": _v(_adx["di_minus"], i),
                    "aroon_up_25": _v(_aroon["up"], i),
                    "aroon_down_25": _v(_aroon["down"], i),
                    "aroon_osc_25": _v(_aroon["oscillator"], i),
                    "chop_14": _v(_chop, i),
                    "ppo": _v(_ppo["ppo"], i),
                    "ppo_signal": _v(_ppo["signal"], i),
                    "ppo_histogram": _v(_ppo["histogram"], i),
                    "roc_12": _v(_roc12, i),
                    "trix_15": _v(_trix15, i),
                    "stoch_k_14": _v(_stoch["k"], i),
                    "stoch_d_3": _v(_stoch["d"], i),
                    "stoch_rsi_14": _v(_stoch_rsi, i),
                    "williams_r_14": _v(_wr, i),
                    "cci_20": _v(_cci, i),
                    "tsi_25_13": _v(_tsi, i),
                    "ultimate_osc": _v(_uo, i),
                    "cmo_14": _v(_cmo, i),
                    "bop": _v(_bop, i),
                    "source_fetch_id": "",
                    "raw_payload_hash": "",
                    "ingestion_run_id": "",
                    "content_hash": "",
                    "version_hash": "",
                    "schema_version": 1,
                    "parser_version": 1,
                    "quality_status": "valid",
                }
            )

    df = pl.DataFrame(rows, infer_schema_length=None)
    if df.is_empty():
        return df

    df = compute_version_hash(df)
    return df.with_columns(
        pl.col("effective_date").cast(pl.Date),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
    )


def _bollinger_fields(close: pl.Series) -> dict[str, pl.Series]:
    """Compute Bollinger Band fields for the single-pass batch."""
    middle = sma(close, 20)
    std = close.rolling_std(window_size=20)
    return {
        "upper": middle + std * 2.0,
        "middle": middle,
        "lower": middle - std * 2.0,
    }
