# Symbol Readouts — Interpretation Layer

A neutral interpretation layer that takes raw measurements (bars, technical indicators, and
later news, mentions, options) and produces **observable, explainable readouts** — never
strategy signals or buy/sell judgments.

A readout answers a clear factual question:

> *Is momentum weak, neutral, constructive, or extended?*
> *Is volatility low, normal, elevated, or extreme?*
> *Is participation quiet, normal, elevated, or unusual?*

## Core Concepts

**Readout** = `(definition, observation)` pair.
- **Definition** — static metadata: name, category, formula, threshold profile, display hints.
- **Observation** — current value + state + orientation + attention + risk + colour.

**State taxonomy** (per readout):
- **Price action:** `up`, `down`, `flat`, `gap_up`, `gap_down`
- **Trend:** `weak`, `trending`, `strong`, `upward`, `downward`, `mixed`
- **Momentum:** `oversold`, `neutral`, `overbought`, `weak`, `constructive`, `positive_cross`, `negative_cross`, `no_cross`
- **Volatility:** `low`, `normal`, `elevated`, `extreme`, `squeeze`, `expanding`, `blown`
- **Participation:** `quiet`, `normal`, `elevated`, `extreme`, `declining`, `surging`
- **Relative strength:** `weak`, `in_line`, `leading`, `improving`, `stable`, `deteriorating`
- **Market regime:** `range`, `breaking_out`, `reversing`, `inside`, `touch`, `break`

**Orientation:** `upward`, `downward`, `mixed`, `not_applicable`

**Attention:** `quiet`, `normal`, `elevated`, `unusual`

**Risk:** `normal`, `elevated`, `extreme`

**Data confidence:** `high`, `medium`, `low`

**Fallback state:** `unavailable` — returned when insufficient history exists for the
requested `as_of`. Never zero, never a default value.

### Colour Policy

| Colour | Meaning | State examples |
|--------|---------|---------------|
| `green` | Constructive | `trending`, `constructive`, `leading`, `surging` |
| `red` | Adverse | `oversold`, `overbought`, `extreme`, `blown`, `reversing` |
| `amber` | Elevated risk/attention | `elevated`, `unusual`, `breaking_out`, `touch` |
| `gray` | Neutral/mixed/unavailable | `neutral`, `mixed`, `normal`, `range`, `unavailable` |

Green and red indicate directionally meaningful states. Amber is a warning — pay
attention but don't assume a directional bias. Gray is baseline or unknown.

## API Shape

### Endpoint

```
GET /v1/dashboard/symbol/{symbol}/readouts
```

### Query Parameters

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `symbol` | str | Path | Ticker symbol |
| `as_of` | ISO 8601 datetime | Yes* | Point-in-time query. Required — use `latest=true` for newest. |
| `latest` | bool | No | Resolve to most recent `available_at` across all sources. |
| `categories` | str | No | Comma-separated category filter (`momentum,volatility`). |
| `readout_ids` | str | No | Comma-separated readout ID filter (`technical.rsi_14,technical.atr_percent`). |

### Response Shape

```json
{
  "symbol": "AAPL",
  "as_of": "2026-06-24T20:00:00Z",
  "readouts": [
    {
      "definition": {
        "definition_id": "technical.rsi_14",
        "name": "RSI (14)",
        "category": "momentum",
        "source_requirements": ["bars_daily", "technical_indicators"],
        "surface": "card",
        "description": "Relative Strength Index over 14 bars — measures speed and magnitude of recent price changes.",
        "question": "Is momentum weak, neutral, constructive, or extended?",
        "calculation_formula": "Wilder RSI over 14 closing-price changes",
        "lookback_bars": 14,
        "parameters": {"period": 14},
        "threshold_profile_id": "rsi_14_v1",
        "display_value_type": "number",
        "display_decimals": 0,
        "display_suffix": "",
        "display_primary_label": "",
        "display_secondary_label": ""
      },
      "observation": {
        "definition_id": "technical.rsi_14",
        "value": 63.1,
        "state": "neutral",
        "orientation": "upward",
        "attention": "normal",
        "risk": "normal",
        "data_confidence": "high",
        "color": "gray",
        "as_of": "2026-06-24T20:00:00Z",
        "calculation_version": "1.0.0"
      }
    }
  ],
  "metadata": {
    "computed_at": "2026-06-24T20:00:01Z",
    "bars_available": 245,
    "readouts_computed": 18,
    "readouts_unavailable": 0
  }
}
```

## Phase 1 — Bar-Derived Readouts (18)

### Price Action (3)

| ID | Name | Formula | Lookback | States | Orientation |
|----|------|---------|----------|--------|-------------|
| `price_action.daily_move` | Daily Move | `(close - prev_close) / prev_close` | 2 | `up`, `down`, `flat` | `upward`, `downward` |
| `price_action.intraday_volatility` | Intraday Volatility | `(high - low) / close` | 2 | `low`, `normal`, `elevated`, `extreme` | `not_applicable` |
| `price_action.gap` | Gap Up/Down | `(open - prev_close) / prev_close` | 2 | `gap_up`, `gap_down`, `no_gap` | `upward`, `downward` |

### Trend (3)

| ID | Name | Formula | Lookback | States | Orientation |
|----|------|---------|----------|--------|-------------|
| `trend.regime` | Trend Regime | ADX-based classification | 15 | `weak`, `trending`, `strong` | `not_applicable` |
| `trend.directional_bias` | Directional Bias | +DI vs -DI comparison | 15 | `upward`, `downward`, `mixed` | — (orientation == state) |
| `trend.strength` | Trend Strength | ADX raw value (percentile) | 15 | `weak`, `moderate`, `strong` | `not_applicable` |

### Momentum (3)

| ID | Name | Formula | Lookback | States | Orientation |
|----|------|---------|----------|--------|-------------|
| `momentum.rsi_14` | RSI (14) | Wilder RSI | 15 | `oversold`, `neutral`, `overbought` | `upward`, `downward` |
| `momentum.macd_cross` | MACD Cross | MACD line vs signal line | 27 | `positive_cross`, `negative_cross`, `no_cross` | — (orientation == state) |
| `momentum.quality` | Momentum Quality | ROC(10) + ROC(21) consensus | 22 | `weak`, `neutral`, `constructive` | `upward`, `downward` |

### Volatility (3)

| ID | Name | Formula | Lookback | States | Orientation |
|----|------|---------|----------|--------|-------------|
| `volatility.atr_percent` | ATR % | ATR / close * 100 (percentile) | 253 | `low`, `normal`, `elevated`, `extreme` | `not_applicable` |
| `volatility.bollinger_width` | Bollinger Width | (upper - lower) / middle | 127 | `squeeze`, `expanding`, `blown` | `not_applicable` |
| `volatility.regime` | Volatility Regime | HV(21) / HV(63) ratio (percentile) | 64 | `low`, `normal`, `elevated`, `extreme` | `not_applicable` |

### Participation (2)

| ID | Name | Formula | Lookback | States | Orientation |
|----|------|---------|----------|--------|-------------|
| `participation.rvol` | Relative Volume | volume / SMA(volume, 21) (percentile) | 22 | `quiet`, `normal`, `elevated`, `extreme` | `not_applicable` |
| `participation.volume_trend` | Volume Trend | volume slope over 5 bars | 6 | `declining`, `neutral`, `surging` | `upward`, `downward` |

### Relative Strength (2)

| ID | Name | Formula | Lookback | States | Orientation |
|----|------|---------|----------|--------|-------------|
| `relative_strength.vs_benchmark` | RS vs Benchmark | symbol return / SPY return over 21 bars | 22 | `weak`, `in_line`, `leading` | `upward`, `downward` |
| `relative_strength.regime` | RS Regime | rolling RS ratio trend | 22 | `improving`, `stable`, `deteriorating` | `upward`, `downward` |

### Market Regime (2)

| ID | Name | Formula | Lookback | States | Orientation |
|----|------|---------|----------|--------|-------------|
| `market_regime.breakout_state` | Breakout State | close relative to 20-bar range | 21 | `range`, `breaking_out`, `reversing` | `upward`, `downward` |
| `market_regime.keltner_touch` | Keltner Touch | touch vs break of Keltner channels | 21 | `inside`, `touch`, `break` | `upward`, `downward` |

## Phase Roadmap

| Phase | Scope | Source Requirements | When |
|-------|-------|-------------------|------|
| 1 | 18 bar-derived readouts (this doc) | `bars_daily`, `technical_indicators`, SPY benchmark | Now |
| 2 | News sentiment + financial signal | `sentiment_annotations` | Future |
| 3 | Mentions + social attention | `attention_metrics`, `entity_mentions` | Future |
| 4 | Event risk + positioning + options | `economic_calendar`, `congress_trades`, options chain | Future |
