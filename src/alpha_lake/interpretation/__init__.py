from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class ReadoutDefinition:
    definition_id: str
    name: str
    category: str
    source_requirements: list[str]
    surface: Literal["card", "detail"]
    description: str
    question: str
    calculation_formula: str
    lookback_bars: int
    parameters: dict = field(default_factory=dict)
    threshold_profile_id: str = ""
    display_value_type: str = "number"
    display_decimals: int = 0
    display_suffix: str = ""
    display_primary_label: str = ""
    display_secondary_label: str = ""
    states: list[str] = field(default_factory=list)
    color_mapping: dict[str, str] = field(
        default_factory=lambda: {
            "unavailable": "gray",
        }
    )


def _default_colors(
    constructive: str = "green",
    adverse: list[str] | None = None,
    amber_states: list[str] | None = None,
) -> dict[str, str]:
    m: dict[str, str] = {"unavailable": "gray"}
    for s in adverse or []:
        m[s] = "red"
    for s in amber_states or []:
        m[s] = "amber"
    m["normal"] = "gray"
    m["neutral"] = "gray"
    m["mixed"] = "gray"
    m["flat"] = "gray"
    m["no_gap"] = "gray"
    m["no_cross"] = "gray"
    m["range"] = "gray"
    m["inside"] = "gray"
    m["in_line"] = "gray"
    m["stable"] = "gray"
    m[constructive] = "green"
    return m


READOUTS: dict[str, ReadoutDefinition] = {}

# --- Price Action ---

READOUTS["price_action.daily_move"] = ReadoutDefinition(
    definition_id="price_action.daily_move",
    name="Daily Move",
    category="price_action",
    source_requirements=["bars_daily"],
    surface="card",
    description="Daily close-to-close percentage change.",
    question="Did the price go up, down, or stay flat today?",
    calculation_formula="(close - prev_close) / prev_close",
    lookback_bars=2,
    parameters={"threshold_profile_id": "daily_move_v1"},
    threshold_profile_id="daily_move_v1",
    display_decimals=2,
    display_suffix="%",
    states=["up", "down", "flat"],
    color_mapping=_default_colors("up", ["down"], []),
)

READOUTS["price_action.intraday_volatility"] = ReadoutDefinition(
    definition_id="price_action.intraday_volatility",
    name="Intraday Volatility",
    category="price_action",
    source_requirements=["bars_daily"],
    surface="card",
    description="Daily range relative to close — how volatile was today's session?",
    question="Was today's range wide, normal, or narrow?",
    calculation_formula="(high - low) / close",
    lookback_bars=2,
    threshold_profile_id="intraday_volatility_v1",
    display_decimals=2,
    display_suffix="%",
    states=["low", "normal", "elevated", "extreme"],
    color_mapping=_default_colors("low", ["extreme"], ["elevated"]),
)

READOUTS["price_action.gap"] = ReadoutDefinition(
    definition_id="price_action.gap",
    name="Gap Up/Down",
    category="price_action",
    source_requirements=["bars_daily"],
    surface="card",
    description="Overnight price gap between prior close and today's open.",
    question="Did the stock gap up, gap down, or open flat?",
    calculation_formula="(open - prev_close) / prev_close",
    lookback_bars=2,
    threshold_profile_id="gap_v1",
    display_decimals=2,
    display_suffix="%",
    states=["gap_up", "gap_down", "no_gap"],
    color_mapping=_default_colors("gap_up", ["gap_down"], []),
)

# --- Trend ---

READOUTS["trend.regime"] = ReadoutDefinition(
    definition_id="trend.regime",
    name="Trend Regime",
    category="trend",
    source_requirements=["bars_daily", "technical_indicators"],
    surface="card",
    description="ADX-based classification: weak, trending, or strongly trending market.",
    question="Is the market trending or range-bound?",
    calculation_formula="ADX(14): <20 weak, 20-39 trending, 40+ strong",
    lookback_bars=15,
    threshold_profile_id="trend_regime_v1",
    display_value_type="text",
    states=["weak", "trending", "strong"],
    color_mapping=_default_colors("trending", [], []),
)

READOUTS["trend.directional_bias"] = ReadoutDefinition(
    definition_id="trend.directional_bias",
    name="Directional Bias",
    category="trend",
    source_requirements=["bars_daily", "technical_indicators"],
    surface="card",
    description="Which directional indicator (+DI or -DI) is dominant.",
    question="Is the trend biased up or down?",
    calculation_formula="+DI vs -DI from ADX(14)",
    lookback_bars=15,
    threshold_profile_id="directional_bias_v1",
    display_value_type="text",
    states=["upward", "downward", "mixed"],
    color_mapping=_default_colors("upward", ["downward"], []),
)

READOUTS["trend.strength"] = ReadoutDefinition(
    definition_id="trend.strength",
    name="Trend Strength",
    category="trend",
    source_requirements=["bars_daily", "technical_indicators"],
    surface="detail",
    description="Raw ADX value classified by percentile.",
    question="How strong is the current trend?",
    calculation_formula="ADX(14) trailing percentile",
    lookback_bars=15,
    threshold_profile_id="trend_strength_v1",
    display_decimals=0,
    states=["weak", "moderate", "strong"],
    color_mapping=_default_colors("strong", ["weak"], []),
)

# --- Momentum ---

READOUTS["momentum.rsi_14"] = ReadoutDefinition(
    definition_id="momentum.rsi_14",
    name="RSI (14)",
    category="momentum",
    source_requirements=["bars_daily", "technical_indicators"],
    surface="card",
    description="Relative Strength Index over 14 bars.",
    question="Is momentum weak, neutral, constructive, or extended?",
    calculation_formula="Wilder RSI over 14 closing-price changes",
    lookback_bars=15,
    threshold_profile_id="rsi_14_v1",
    display_decimals=0,
    states=["oversold", "neutral", "overbought"],
    color_mapping=_default_colors("oversold", ["overbought"], []),
)

READOUTS["momentum.macd_cross"] = ReadoutDefinition(
    definition_id="momentum.macd_cross",
    name="MACD Cross",
    category="momentum",
    source_requirements=["bars_daily", "technical_indicators"],
    surface="card",
    description="MACD line crossed above (positive) or below (negative) its signal line.",
    question="Is momentum accelerating or decelerating?",
    calculation_formula="MACD(12,26,9) line vs signal line",
    lookback_bars=27,
    threshold_profile_id="macd_cross_v1",
    display_value_type="text",
    states=["positive_cross", "negative_cross", "no_cross"],
    color_mapping=_default_colors("positive_cross", ["negative_cross"], []),
)

READOUTS["momentum.quality"] = ReadoutDefinition(
    definition_id="momentum.quality",
    name="Momentum Quality",
    category="momentum",
    source_requirements=["bars_daily"],
    surface="detail",
    description="Consensus of ROC(10) and ROC(21) — are both positive, both negative, or mixed?",
    question="Is short-term momentum broad or conflicting?",
    calculation_formula="ROC(10) + ROC(21) consensus: both positive, mixed, both negative",
    lookback_bars=22,
    threshold_profile_id="momentum_quality_v1",
    display_value_type="text",
    states=["weak", "neutral", "constructive"],
    color_mapping=_default_colors("constructive", ["weak"], []),
)

# --- Volatility ---

READOUTS["volatility.atr_percent"] = ReadoutDefinition(
    definition_id="volatility.atr_percent",
    name="ATR %",
    category="volatility",
    source_requirements=["bars_daily", "technical_indicators"],
    surface="card",
    description="Average True Range as percentage of close, trailing percentile.",
    question="Is the average daily range low, normal, elevated, or extreme?",
    calculation_formula="ATR(14) / close * 100, trailing 252-day percentile",
    lookback_bars=253,
    threshold_profile_id="atr_percent_v1",
    display_decimals=2,
    display_suffix="%",
    states=["low", "normal", "elevated", "extreme"],
    color_mapping=_default_colors("low", ["extreme"], ["elevated"]),
)

READOUTS["volatility.bollinger_width"] = ReadoutDefinition(
    definition_id="volatility.bollinger_width",
    name="Bollinger Width",
    category="volatility",
    source_requirements=["bars_daily", "technical_indicators"],
    surface="card",
    description="Bollinger Band width — squeezed (low volatility), expanding, or blown (extreme).",
    question="Is volatility compressing, expanding, or at extreme levels?",
    calculation_formula="(upper_bb - lower_bb) / middle_bb, trailing percentile",
    lookback_bars=127,
    threshold_profile_id="bollinger_width_v1",
    display_value_type="text",
    states=["squeeze", "expanding", "blown"],
    color_mapping=_default_colors("expanding", ["blown"], ["squeeze"]),
)

READOUTS["volatility.regime"] = ReadoutDefinition(
    definition_id="volatility.regime",
    name="Volatility Regime",
    category="volatility",
    source_requirements=["bars_daily"],
    surface="detail",
    description="Ratio of short-term to long-term realized volatility.",
    question="Is the volatility regime low, normal, elevated, or extreme?",
    calculation_formula="HV(21) / HV(63) ratio, trailing percentile",
    lookback_bars=64,
    threshold_profile_id="volatility_regime_v1",
    display_value_type="text",
    states=["low", "normal", "elevated", "extreme"],
    color_mapping=_default_colors("low", ["extreme"], ["elevated"]),
)

# --- Participation ---

READOUTS["participation.rvol"] = ReadoutDefinition(
    definition_id="participation.rvol",
    name="Relative Volume",
    category="participation",
    source_requirements=["bars_daily", "technical_indicators"],
    surface="card",
    description="Today's volume vs 21-day average, measured against trailing distribution.",
    question="Is trading volume quiet, normal, elevated, or extreme?",
    calculation_formula="volume / SMA(volume, 21), trailing percentile",
    lookback_bars=22,
    threshold_profile_id="rvol_v1",
    display_decimals=2,
    states=["quiet", "normal", "elevated", "extreme"],
    color_mapping=_default_colors("quiet", ["extreme"], ["elevated"]),
)

READOUTS["participation.volume_trend"] = ReadoutDefinition(
    definition_id="participation.volume_trend",
    name="Volume Trend",
    category="participation",
    source_requirements=["bars_daily"],
    surface="detail",
    description="Short-term volume direction — is volume declining, stable, or surging?",
    question="Is volume trending up, down, or flat?",
    calculation_formula="volume slope over 5 bars",
    lookback_bars=6,
    threshold_profile_id="volume_trend_v1",
    display_value_type="text",
    states=["declining", "neutral", "surging"],
    color_mapping=_default_colors("surging", ["declining"], []),
)

# --- Relative Strength ---

READOUTS["relative_strength.vs_benchmark"] = ReadoutDefinition(
    definition_id="relative_strength.vs_benchmark",
    name="RS vs Benchmark",
    category="relative_strength",
    source_requirements=["bars_daily", "benchmark_bars"],
    surface="card",
    description="21-bar return of symbol divided by 21-bar return of SPY.",
    question="Is the symbol outperforming, in line with, or lagging the benchmark?",
    calculation_formula="(1 + R_symbol(21)) / (1 + R_SPY(21)) - 1",
    lookback_bars=22,
    threshold_profile_id="rs_vs_benchmark_v1",
    display_value_type="text",
    states=["weak", "in_line", "leading"],
    color_mapping=_default_colors("leading", ["weak"], []),
)

READOUTS["relative_strength.regime"] = ReadoutDefinition(
    definition_id="relative_strength.regime",
    name="RS Regime",
    category="relative_strength",
    source_requirements=["bars_daily", "benchmark_bars"],
    surface="detail",
    description="Trend of the rolling RS ratio — improving, stable, or deteriorating?",
    question="Is relative performance getting better, stable, or worse?",
    calculation_formula="rolling RS ratio slope over 5 periods",
    lookback_bars=22,
    threshold_profile_id="rs_regime_v1",
    display_value_type="text",
    states=["improving", "stable", "deteriorating"],
    color_mapping=_default_colors("improving", ["deteriorating"], []),
)

# --- Market Regime ---

READOUTS["market_regime.breakout_state"] = ReadoutDefinition(
    definition_id="market_regime.breakout_state",
    name="Breakout State",
    category="market_regime",
    source_requirements=["bars_daily", "technical_indicators"],
    surface="card",
    description="Is the close inside the 20-bar range, breaking out above, or reversing below?",
    question="Is the price in a range, breaking out, or reversing?",
    calculation_formula="close vs rolling 20-bar high/low range",
    lookback_bars=21,
    threshold_profile_id="breakout_state_v1",
    display_value_type="text",
    states=["range", "breaking_out", "reversing"],
    color_mapping=_default_colors("breaking_out", ["reversing"], []),
)

READOUTS["market_regime.keltner_touch"] = ReadoutDefinition(
    definition_id="market_regime.keltner_touch",
    name="Keltner Touch",
    category="market_regime",
    source_requirements=["bars_daily", "technical_indicators"],
    surface="detail",
    description="Is the close touching or breaking Keltner Channel bands?",
    question="Is the price at the edge of or outside its typical range?",
    calculation_formula="close vs Keltner Channel(20, 2x ATR) upper/lower",
    lookback_bars=21,
    threshold_profile_id="keltner_touch_v1",
    display_value_type="text",
    states=["inside", "touch", "break"],
    color_mapping=_default_colors("inside", ["break"], ["touch"]),
)

# --- Derived helpers ---

CATEGORIES: dict[str, str] = {
    "price_action": "Price Action",
    "trend": "Trend",
    "momentum": "Momentum",
    "volatility": "Volatility",
    "participation": "Participation",
    "relative_strength": "Relative Strength",
    "market_regime": "Market Regime",
}


__all__ = [
    "ReadoutDefinition",
    "READOUTS",
]
