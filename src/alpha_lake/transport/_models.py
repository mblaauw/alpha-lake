from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    row_count: int
    snapshot_count: int
    synthetic_mode: bool


class SymbolInfo(BaseModel):
    security_id: str
    symbol: str
    name: str


class DatasetInfo(BaseModel):
    dataset: str
    tier: str
    supported: bool
    sla: bool
    rows: int
    latest_effective_date: str
    status: str
    schema_version: int


class DatasetDetailResponse(BaseModel):
    dataset: str
    columns: list[str]
    rows: list[dict[str, Any]]
    fetched_at: str


class BarsSummaryResponse(BaseModel):
    symbol: str
    security_id: str
    name: str
    last: float
    change_pct: float
    latest_date: str
    quality_status: str
    source_id: str | None = None
    trend: list[float]
    volume: list[float]
    sma_20: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    ema_12: float | None = None
    ema_26: float | None = None
    rsi: float | None = None
    macd: float | None = None
    macd_ema: float | None = None
    macd_hist: float | None = None
    bb_upper: float | None = None
    bb_middle: float | None = None
    bb_lower: float | None = None
    atr: float | None = None
    atr_pct: float | None = None
    obv: float | None = None
    vwap: float | None = None
    vol_ratio: float | None = None
    dollar_volume: float | None = None
    avg_dollar_volume_20: float | None = None
    rvol: float | None = None
    return_1d: float | None = None
    return_5d: float | None = None
    return_21d: float | None = None
    return_63d: float | None = None
    gap_pct: float | None = None
    pct_off_52w_high: float | None = None
    pct_off_52w_low: float | None = None
    is_new_52w_high: bool | None = None
    is_new_52w_low: bool | None = None
    realized_vol_21: float | None = None
    realized_vol_63: float | None = None


class LeaderboardRow(BaseModel):
    security_id: str
    symbol: str
    name: str = ""
    mentions: int = 0
    upvotes: int | None = None
    rank: Any = None
    cohort: Any = None
    mention_delta_pct: Any = None
    upvote_ratio: Any = None
    upvote_delta_pct: Any = None
    positive_ratio: Any = None
    neutral_ratio: Any = None
    negative_ratio: Any = None
    mean_score: Any = None
    total_messages: Any = None
    trend: list[float] = []


class MacroSeriesRow(BaseModel):
    series_id: str = ""
    effective_date: str = ""
    value: float | None = None


class TransactionRow(BaseModel):
    effective_date: str = ""
    available_at: str = ""
    security_id: str = ""
    transaction_type: str = ""
    shares: float | None = None
    price: float | None = None
    value: float | None = None


class ReadoutDefinition(BaseModel):
    definition_id: str
    name: str
    category: str
    source_requirements: dict[str, Any] = {}
    surface: str = ""
    description: str = ""
    question: str = ""
    calculation_formula: str = ""
    lookback_bars: int = 0
    parameters: dict[str, Any] = {}
    threshold_profile_id: str = ""
    display_value_type: str = "float"
    display_decimals: int = 2
    display_suffix: str = ""
    display_primary_label: str = ""
    display_secondary_label: str = ""


class ReadoutObservation(BaseModel):
    definition_id: str
    state: str = "unavailable"
    value: Any = None
    numeric_value: float | None = None
    threshold_zone: str | None = None
    is_notable: bool = False
    display_value: str | None = None
    message: str | None = None
    computed_at: str | None = None


class ReadoutItem(BaseModel):
    definition: ReadoutDefinition
    observation: ReadoutObservation


class ReadoutMetadata(BaseModel):
    computed_at: str
    bars_available: int = 0
    readouts_computed: int = 0
    readouts_unavailable: int = 0
    error: str | None = None


class ReadoutsResponse(BaseModel):
    symbol: str
    as_of: str
    readouts: list[ReadoutItem]
    metadata: ReadoutMetadata
