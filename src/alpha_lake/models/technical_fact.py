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
