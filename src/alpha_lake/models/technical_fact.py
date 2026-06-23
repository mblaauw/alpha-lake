from __future__ import annotations

import datetime

import patito as pt
from patito import Field


class TechnicalIndicatorFact(pt.Model):
    model_config = {"coerce_nulls": True}
    security_id: str
    effective_date: datetime.date
    available_at: datetime.datetime
    source_id: str
    sma_20: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    ema_12: float | None = None
    ema_26: float | None = None
    rsi_14: float | None = Field(None, ge=0, le=100)
    bb_upper: float | None = None
    bb_middle: float | None = None
    bb_lower: float | None = None
    atr_14: float | None = None
    obv: float | None = None
    vwap: float | None = None
    macd: float | None = None
    macd_ema: float | None = None
    macd_histogram: float | None = None
    return_1: float | None = None
    return_5: float | None = None
    return_21: float | None = None
    return_63: float | None = None
    return_126: float | None = None
    return_252: float | None = None
    # ── Momentum & Oscillator ─────────────────────────────────────────────
    adx_14: float | None = None
    di_plus_14: float | None = None
    di_minus_14: float | None = None
    aroon_up_25: float | None = None
    aroon_down_25: float | None = None
    aroon_osc_25: float | None = None
    chop_14: float | None = None
    ppo: float | None = None
    ppo_signal: float | None = None
    ppo_histogram: float | None = None
    roc_12: float | None = None
    trix_15: float | None = None
    stoch_k_14: float | None = None
    stoch_d_3: float | None = None
    stoch_rsi_14: float | None = None
    williams_r_14: float | None = None
    cci_20: float | None = None
    tsi_25_13: float | None = None
    ultimate_osc: float | None = None
    cmo_14: float | None = None
    bop: float | None = None
    dist_to_ma_20: float | None = None
    dist_to_ma_50: float | None = None
    dist_to_ma_200: float | None = None
    above_ma_20: bool | None = None
    above_ma_50: bool | None = None
    above_ma_200: bool | None = None
    atr_pct: float | None = None
    realized_vol_21: float | None = None
    realized_vol_63: float | None = None
    rvol: float | None = None
    dollar_volume: float | None = None
    avg_dollar_volume_20: float | None = None
    # ── Volume & Money Flow ───────────────────────────────────────────────
    ad_line: float | None = None
    cmf_20: float | None = None
    chaikin_osc: float | None = None
    mfi_14: float | None = None
    vpt: float | None = None
    force_index_13: float | None = None
    eom_14: float | None = None
    obv_slope_20: float | None = None
    volume_spike: bool | None = None
    # ── Volatility & Structure ────────────────────────────────────────────
    keltner_upper: float | None = None
    keltner_middle: float | None = None
    keltner_lower: float | None = None
    donchian_upper: float | None = None
    donchian_middle: float | None = None
    donchian_lower: float | None = None
    percent_b: float | None = None
    bandwidth: float | None = None
    bb_squeeze: bool | None = None
    range_expansion: float | None = None
    true_range: float | None = None
    rolling_std_20: float | None = None
    wma_20: float | None = None
    kama_10: float | None = None
    linreg_slope_20: float | None = None
    linreg_channel_upper: float | None = None
    linreg_channel_middle: float | None = None
    linreg_channel_lower: float | None = None
    pivot_high: float | None = None
    pivot_low: float | None = None
    inside_bar: bool | None = None
    outside_bar: bool | None = None
    gap_fill: bool | None = None
    # ── Utility ───────────────────────────────────────────────────────────
    log_return: float | None = None
    ma_stack: float | None = None
    ma_slope_20: float | None = None
    ma_slope_50: float | None = None
    ma_slope_200: float | None = None
    rsi_divergence: float | None = None
    # ── Relative Performance (requires SPY bars) ──────────────────────────
    beta_20d: float | None = None
    beta_60d: float | None = None
    alpha: float | None = None
    rs_spy_20d: float | None = None
    rs_spy_60d: float | None = None
    corr_spy: float | None = None
    pct_off_52w_high: float | None = None
    pct_off_52w_low: float | None = None
    is_new_52w_high: bool | None = None
    is_new_52w_low: bool | None = None
    gap_pct: float | None = None
    source_fetch_id: str = ""
    raw_payload_hash: str = ""
    ingestion_run_id: str = ""
    content_hash: str = ""
    version_hash: str = ""
    schema_version: int = 1
    parser_version: int = 1
    quality_status: str = "valid"
