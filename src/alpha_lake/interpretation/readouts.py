from __future__ import annotations

import datetime
import math
from dataclasses import dataclass
from typing import Any

import polars as pl

from alpha_lake.derived.indicators import (
    adx,
    atr,
    atr_pct,
    bandwidth,
    compute_relative_strength,
    keltner_channels,
    macd,
    realized_vol,
    relative_volume,
    returns,
    rsi,
    sma,
)
from alpha_lake.interpretation import READOUTS, ReadoutDefinition
from alpha_lake.interpretation.profiles import (
    ThresholdProfile,
    resolve_state,
)


@dataclass(frozen=True)
class ReadoutObservation:
    definition_id: str
    value: float | None
    state: str
    orientation: str
    attention: str
    risk: str
    data_confidence: str
    color: str
    as_of: datetime.datetime
    calculation_version: str = "1.0.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "definition_id": self.definition_id,
            "value": self.value,
            "state": self.state,
            "orientation": self.orientation,
            "attention": self.attention,
            "risk": self.risk,
            "data_confidence": self.data_confidence,
            "color": self.color,
            "as_of": self.as_of.isoformat(),
            "calculation_version": self.calculation_version,
        }


_CALC_VERSION = "1.0.0"


def _last_or_none(s: pl.Series) -> float | None:
    if len(s) == 0:
        return None
    v = s[-1]
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return None
    return float(v)


def _prev_or_none(s: pl.Series) -> float | None:
    if len(s) < 2:
        return None
    v = s[-2]
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return None
    return float(v)


def _value_at(s: pl.Series, idx: int) -> float | None:
    if idx < 0 or idx >= len(s):
        return None
    v = s[idx]
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return None
    return float(v)


def _make_obs(
    defn: ReadoutDefinition,
    value: float | None,
    state: str,
    orientation: str = "not_applicable",
    attention: str = "normal",
    risk: str = "normal",
    data_confidence: str = "high",
    as_of: datetime.datetime | None = None,
) -> ReadoutObservation:
    color = defn.color_mapping.get(state, "gray")
    return ReadoutObservation(
        definition_id=defn.definition_id,
        value=value,
        state=state,
        orientation=orientation,
        attention=attention,
        risk=risk,
        data_confidence=data_confidence,
        color=color,
        as_of=as_of or datetime.datetime.now(datetime.UTC),
        calculation_version=_CALC_VERSION,
    )


# --- Price Action ---


def compute_daily_move(
    bars: pl.DataFrame,
    as_of: datetime.datetime,
    definition: ReadoutDefinition,
    profile: ThresholdProfile,
) -> ReadoutObservation:
    close = bars["close"]
    prev_close = _prev_or_none(close)
    curr_close = _last_or_none(close)
    if prev_close is None or curr_close is None or prev_close == 0:
        return _make_obs(definition, None, "unavailable", as_of=as_of)
    val = (curr_close - prev_close) / prev_close
    state = resolve_state(profile, val, lookback_bars=2)
    orientation = "upward" if val > 0 else "downward" if val < 0 else "mixed"
    return _make_obs(definition, round(val, 6), state, orientation, as_of=as_of)


def compute_intraday_volatility(
    bars: pl.DataFrame,
    as_of: datetime.datetime,
    definition: ReadoutDefinition,
    profile: ThresholdProfile,
) -> ReadoutObservation:
    high = _last_or_none(bars["high"])
    low = _last_or_none(bars["low"])
    close = _last_or_none(bars["close"])
    if high is None or low is None or close is None or close == 0:
        return _make_obs(definition, None, "unavailable", as_of=as_of)
    val = (high - low) / close
    hist = (bars["high"] - bars["low"]) / bars["close"]
    state = resolve_state(profile, val, hist, definition.lookback_bars)
    attention = "elevated" if state in ("elevated", "extreme") else "normal"
    risk = "elevated" if state in ("elevated", "extreme") else "normal"
    return _make_obs(definition, round(val, 6), state, attention=attention, risk=risk, as_of=as_of)


def compute_gap(
    bars: pl.DataFrame,
    as_of: datetime.datetime,
    definition: ReadoutDefinition,
    profile: ThresholdProfile,
) -> ReadoutObservation:
    open_ = _last_or_none(bars["open"])
    prev_close = _prev_or_none(bars["close"])
    if open_ is None or prev_close is None or prev_close == 0:
        return _make_obs(definition, None, "unavailable", as_of=as_of)
    val = (open_ - prev_close) / prev_close
    state = resolve_state(profile, val, lookback_bars=2)
    orientation = "upward" if val > 0 else "downward" if val < 0 else "mixed"
    return _make_obs(definition, round(val, 6), state, orientation, as_of=as_of)


# --- Trend ---


def compute_trend_regime(
    bars: pl.DataFrame,
    as_of: datetime.datetime,
    definition: ReadoutDefinition,
    profile: ThresholdProfile,
    indicators: dict[str, float] | None = None,
) -> ReadoutObservation:
    if indicators is not None and "adx_14" in indicators and indicators["adx_14"] is not None:
        val = indicators["adx_14"]
    else:
        _adx = adx(bars["high"], bars["low"], bars["close"], 14)
        val = _last_or_none(_adx["adx"])
    if val is None:
        return _make_obs(definition, None, "unavailable", as_of=as_of)
    state = resolve_state(profile, val, lookback_bars=15)
    return _make_obs(definition, round(val, 2), state, as_of=as_of)


def compute_directional_bias(
    bars: pl.DataFrame,
    as_of: datetime.datetime,
    definition: ReadoutDefinition,
    profile: ThresholdProfile,
    indicators: dict[str, float] | None = None,
) -> ReadoutObservation:
    if indicators is not None:
        di_plus = indicators.get("di_plus_14")
        di_minus = indicators.get("di_minus_14")
    else:
        _adx = adx(bars["high"], bars["low"], bars["close"], 14)
        di_plus = _last_or_none(_adx["di_plus"])
        di_minus = _last_or_none(_adx["di_minus"])
    if di_plus is None or di_minus is None:
        return _make_obs(definition, None, "unavailable", as_of=as_of)
    diff = di_plus - di_minus
    state = resolve_state(profile, diff, lookback_bars=15)
    orientation = state
    return _make_obs(definition, round(diff, 2), state, orientation=orientation, as_of=as_of)


def compute_trend_strength(
    bars: pl.DataFrame,
    as_of: datetime.datetime,
    definition: ReadoutDefinition,
    profile: ThresholdProfile,
    indicators: dict[str, float] | None = None,
) -> ReadoutObservation:
    if indicators is not None and "adx_14" in indicators and indicators["adx_14"] is not None:
        val = indicators["adx_14"]
    else:
        _adx = adx(bars["high"], bars["low"], bars["close"], 14)
        val = _last_or_none(_adx["adx"])
    if val is None:
        return _make_obs(definition, None, "unavailable", as_of=as_of)
    hist = bars["close"].diff().abs().rolling_mean(window_size=14)
    state = resolve_state(profile, val, hist, definition.lookback_bars)
    return _make_obs(definition, round(val, 2), state, as_of=as_of)


# --- Momentum ---


def compute_rsi_14(
    bars: pl.DataFrame,
    as_of: datetime.datetime,
    definition: ReadoutDefinition,
    profile: ThresholdProfile,
    indicators: dict[str, float] | None = None,
) -> ReadoutObservation:
    if indicators is not None and "rsi_14" in indicators and indicators["rsi_14"] is not None:
        val = indicators["rsi_14"]
    else:
        _rsi = rsi(bars["close"], 14)
        val = _last_or_none(_rsi)
    if val is None:
        return _make_obs(definition, None, "unavailable", as_of=as_of)
    state = resolve_state(profile, val, lookback_bars=15)
    orientation = "upward" if val > 50 else "downward" if val < 50 else "mixed"
    return _make_obs(definition, round(val, 2), state, orientation, as_of=as_of)


def compute_macd_cross(
    bars: pl.DataFrame,
    as_of: datetime.datetime,
    definition: ReadoutDefinition,
    profile: ThresholdProfile,
    indicators: dict[str, float] | None = None,
) -> ReadoutObservation:
    if indicators is not None and "macd" in indicators and indicators["macd"] is not None:
        macd_line = indicators["macd"]
        raw_ema = indicators.get("macd_ema")
        macd_ema = raw_ema if raw_ema is not None else indicators.get("macd_signal", 0)
    else:
        _macd = macd(bars["close"], 12, 26, 9)
        macd_line = _last_or_none(_macd["macd"])
        macd_ema = _last_or_none(_macd["macd_ema"])
    if macd_line is None or macd_ema is None:
        return _make_obs(definition, None, "unavailable", as_of=as_of)
    diff = macd_line - macd_ema
    state = resolve_state(profile, diff, lookback_bars=27)
    orientation = state
    return _make_obs(definition, round(diff, 4), state, orientation=orientation, as_of=as_of)


def compute_momentum_quality(
    bars: pl.DataFrame,
    as_of: datetime.datetime,
    definition: ReadoutDefinition,
    profile: ThresholdProfile,
) -> ReadoutObservation:
    close = bars["close"]
    roc10 = _last_or_none(close / close.shift(10) - 1)
    roc21 = _last_or_none(close / close.shift(21) - 1)
    if roc10 is None or roc21 is None or not math.isfinite(roc10) or not math.isfinite(roc21):
        return _make_obs(definition, None, "unavailable", as_of=as_of)
    avg = (roc10 + roc21) / 2
    state = resolve_state(profile, avg, lookback_bars=22)
    orientation = (
        "upward" if roc10 > 0 and roc21 > 0 else "downward" if roc10 < 0 and roc21 < 0 else "mixed"
    )
    return _make_obs(definition, round(avg, 6), state, orientation, as_of=as_of)


# --- Volatility ---


def compute_atr_percent(
    bars: pl.DataFrame,
    as_of: datetime.datetime,
    definition: ReadoutDefinition,
    profile: ThresholdProfile,
    indicators: dict[str, float] | None = None,
) -> ReadoutObservation:
    if indicators is not None and "atr_pct" in indicators and indicators["atr_pct"] is not None:
        val = indicators["atr_pct"]
    else:
        _atr = atr(bars["high"], bars["low"], bars["close"], 14)
        _atr_pct_series = atr_pct(_atr, bars["close"])
        val = _last_or_none(_atr_pct_series)
    if val is None:
        return _make_obs(definition, None, "unavailable", as_of=as_of)
    hist = atr_pct(atr(bars["high"], bars["low"], bars["close"], 14), bars["close"])
    state = resolve_state(profile, val, hist, definition.lookback_bars)
    attention = "elevated" if state in ("elevated", "extreme") else "normal"
    risk = "elevated" if state in ("elevated", "extreme") else "normal"
    return _make_obs(definition, round(val, 4), state, attention=attention, risk=risk, as_of=as_of)


def compute_bollinger_width(
    bars: pl.DataFrame,
    as_of: datetime.datetime,
    definition: ReadoutDefinition,
    profile: ThresholdProfile,
    indicators: dict[str, float] | None = None,
) -> ReadoutObservation:
    if indicators is not None and "bandwidth" in indicators and indicators["bandwidth"] is not None:
        val = indicators["bandwidth"]
    else:
        bb = sma(bars["close"], 20)
        std = bars["close"].rolling_std(window_size=20)
        upper = bb + std * 2.0
        lower = bb - std * 2.0
        _bw = (upper - lower) / bb
        val = _last_or_none(_bw)
    if val is None:
        return _make_obs(definition, None, "unavailable", as_of=as_of)
    hist = bandwidth(
        sma(bars["close"], 20) + bars["close"].rolling_std(window_size=20) * 2.0,
        sma(bars["close"], 20) - bars["close"].rolling_std(window_size=20) * 2.0,
        sma(bars["close"], 20),
    )
    state = resolve_state(profile, val, hist, definition.lookback_bars)
    if state == "unavailable":
        attention = "normal"
        risk = "normal"
    else:
        attention = (
            "elevated"
            if state in ("expanding", "blown")
            else "normal"
            if state == "squeeze"
            else "quiet"
        )
        risk = "extreme" if state == "blown" else "elevated" if state == "expanding" else "normal"
    return _make_obs(definition, round(val, 4), state, attention=attention, risk=risk, as_of=as_of)


def compute_volatility_regime(
    bars: pl.DataFrame,
    as_of: datetime.datetime,
    definition: ReadoutDefinition,
    profile: ThresholdProfile,
) -> ReadoutObservation:
    close = bars["close"]
    hv21 = _last_or_none(realized_vol(close, 21))
    hv63 = _last_or_none(realized_vol(close, 63))
    if hv21 is None or hv63 is None or hv63 == 0 or not math.isfinite(hv21):
        return _make_obs(definition, None, "unavailable", as_of=as_of)
    val = hv21 / hv63
    hist = realized_vol(close, 21) / realized_vol(close, 63)
    state = resolve_state(profile, val, hist, definition.lookback_bars)
    attention = "elevated" if state in ("elevated", "extreme") else "normal"
    risk = "elevated" if state in ("elevated", "extreme") else "normal"
    return _make_obs(definition, round(val, 4), state, attention=attention, risk=risk, as_of=as_of)


# --- Participation ---


def compute_rvol(
    bars: pl.DataFrame,
    as_of: datetime.datetime,
    definition: ReadoutDefinition,
    profile: ThresholdProfile,
    indicators: dict[str, float] | None = None,
) -> ReadoutObservation:
    if indicators is not None and "rvol" in indicators and indicators["rvol"] is not None:
        val = indicators["rvol"]
    else:
        _rvol_series = relative_volume(bars["volume"], 20)
        val = _last_or_none(_rvol_series)
    if val is None:
        return _make_obs(definition, None, "unavailable", as_of=as_of)
    hist = relative_volume(bars["volume"], 20)
    state = resolve_state(profile, val, hist, definition.lookback_bars)
    attention = "elevated" if state in ("elevated", "extreme") else "normal"
    risk = "elevated" if state == "extreme" else "normal"
    return _make_obs(definition, round(val, 4), state, attention=attention, risk=risk, as_of=as_of)


def compute_volume_trend(
    bars: pl.DataFrame,
    as_of: datetime.datetime,
    definition: ReadoutDefinition,
    profile: ThresholdProfile,
) -> ReadoutObservation:
    volume = bars["volume"]
    if len(volume) < 5:
        return _make_obs(definition, None, "unavailable", as_of=as_of)
    recent = [float(volume[i]) for i in range(-5, 0) if volume[i] is not None]
    if len(recent) < 5:
        return _make_obs(definition, None, "unavailable", as_of=as_of)
    x_mean = 2.0
    x_ss = 10.0
    y_mean = sum(recent) / 5.0
    slope = sum((i - x_mean) * (recent[i] - y_mean) for i in range(5)) / x_ss
    norm_slope = slope / y_mean if y_mean else 0.0
    state = resolve_state(profile, norm_slope, lookback_bars=6)
    orientation = "upward" if norm_slope > 0 else "downward" if norm_slope < 0 else "mixed"
    attention = "elevated" if state == "surging" else "normal"
    return _make_obs(
        definition, round(norm_slope, 4), state, orientation, attention=attention, as_of=as_of
    )


# --- Relative Strength ---


def compute_rs_vs_benchmark(
    bars: pl.DataFrame,
    as_of: datetime.datetime,
    definition: ReadoutDefinition,
    profile: ThresholdProfile,
    benchmark_bars: pl.DataFrame | None = None,
) -> ReadoutObservation:
    if benchmark_bars is None or benchmark_bars.is_empty():
        return _make_obs(definition, None, "unavailable", as_of=as_of)
    _ret21 = _last_or_none(returns(bars["close"], 21))
    _bm_ret21 = _last_or_none(returns(benchmark_bars["close"], 21))
    if _ret21 is None or _bm_ret21 is None or _bm_ret21 <= -1:
        return _make_obs(definition, None, "unavailable", as_of=as_of)
    val = (1.0 + _ret21) / (1.0 + _bm_ret21) - 1.0
    state = resolve_state(profile, val, lookback_bars=22)
    orientation = "upward" if val > 0 else "downward" if val < 0 else "mixed"
    return _make_obs(definition, round(val, 6), state, orientation, as_of=as_of)


def compute_rs_regime(
    bars: pl.DataFrame,
    as_of: datetime.datetime,
    definition: ReadoutDefinition,
    profile: ThresholdProfile,
    benchmark_bars: pl.DataFrame | None = None,
) -> ReadoutObservation:
    if benchmark_bars is None or benchmark_bars.is_empty():
        return _make_obs(definition, None, "unavailable", as_of=as_of)
    sym_rets_21 = returns(bars["close"], 21)
    bm_rets_21 = returns(benchmark_bars["close"], 21)
    if len(sym_rets_21) < 5 or len(bm_rets_21) < 5:
        return _make_obs(definition, None, "unavailable", as_of=as_of)
    rs_series = compute_relative_strength(
        bars["close"].diff() / bars["close"].shift(1),
        benchmark_bars["close"].diff() / benchmark_bars["close"].shift(1),
        21,
    )
    rs_slope = _compute_slope(rs_series, 5)
    if rs_slope is None:
        return _make_obs(definition, None, "unavailable", as_of=as_of)
    state = resolve_state(profile, rs_slope, lookback_bars=22)
    orientation = "upward" if rs_slope > 0 else "downward" if rs_slope < 0 else "mixed"
    return _make_obs(definition, round(rs_slope, 6), state, orientation, as_of=as_of)


# --- Market Regime ---


def compute_breakout_state(
    bars: pl.DataFrame,
    as_of: datetime.datetime,
    definition: ReadoutDefinition,
    profile: ThresholdProfile,
) -> ReadoutObservation:
    close = bars["close"]
    if len(close) < 21:
        return _make_obs(definition, None, "unavailable", as_of=as_of)
    high_20 = close.rolling_max(window_size=20)
    low_20 = close.rolling_min(window_size=20)
    last_close = _last_or_none(close)
    last_high = _last_or_none(high_20)
    last_low = _last_or_none(low_20)
    if last_close is None or last_high is None or last_low is None or last_high == last_low:
        return _make_obs(definition, None, "unavailable", as_of=as_of)
    val = (last_close - last_low) / (last_high - last_low)
    state = resolve_state(profile, val, lookback_bars=21)
    orientation = (
        "upward" if state == "breaking_out" else "downward" if state == "reversing" else "mixed"
    )
    attention = "elevated" if state in ("breaking_out", "reversing") else "normal"
    return _make_obs(
        definition, round(val, 4), state, orientation, attention=attention, as_of=as_of
    )


def compute_keltner_touch(
    bars: pl.DataFrame,
    as_of: datetime.datetime,
    definition: ReadoutDefinition,
    profile: ThresholdProfile,
    indicators: dict[str, float] | None = None,
) -> ReadoutObservation:
    if indicators is not None and all(
        k in indicators for k in ("keltner_upper", "keltner_lower", "keltner_middle")
    ):
        ku = indicators["keltner_upper"]
        kl = indicators["keltner_lower"]
        km = indicators["keltner_middle"]
    else:
        _kc = keltner_channels(bars["high"], bars["low"], bars["close"], 20, 10, 2.0)
        ku = _last_or_none(_kc["upper"])
        kl = _last_or_none(_kc["lower"])
        km = _last_or_none(_kc["middle"])
    close = _last_or_none(bars["close"])
    if close is None or ku is None or kl is None or km is None or km == 0:
        return _make_obs(definition, None, "unavailable", as_of=as_of)
    range_ = ku - kl
    if range_ == 0:
        return _make_obs(definition, None, "unavailable", as_of=as_of)
    dist_from_mid = (close - km) / (range_ / 2)
    state = resolve_state(profile, abs(dist_from_mid), lookback_bars=21)
    orientation = "upward" if dist_from_mid > 0 else "downward" if dist_from_mid < 0 else "mixed"
    attention = "elevated" if state in ("touch", "break") else "normal"
    risk = "elevated" if state == "break" else "normal"
    return _make_obs(
        definition,
        round(dist_from_mid, 4),
        state,
        orientation,
        attention=attention,
        risk=risk,
        as_of=as_of,
    )


# --- Helpers ---


def _compute_slope(series: pl.Series, window: int = 5) -> float | None:
    if len(series) < window:
        return None
    vals = [float(series[i]) for i in range(-window, 0) if series[i] is not None]
    if len(vals) < window:
        return None
    x_mean = (window - 1.0) / 2.0
    x_ss = sum((i - x_mean) ** 2 for i in range(window))
    y_mean = sum(vals) / window
    return sum((i - x_mean) * (vals[i] - y_mean) for i in range(window)) / x_ss


# --- Dispatch Map ---

_READOUT_COMPUTERS: dict[str, Any] = {
    "price_action.daily_move": compute_daily_move,
    "price_action.intraday_volatility": compute_intraday_volatility,
    "price_action.gap": compute_gap,
    "trend.regime": compute_trend_regime,
    "trend.directional_bias": compute_directional_bias,
    "trend.strength": compute_trend_strength,
    "momentum.rsi_14": compute_rsi_14,
    "momentum.macd_cross": compute_macd_cross,
    "momentum.quality": compute_momentum_quality,
    "volatility.atr_percent": compute_atr_percent,
    "volatility.bollinger_width": compute_bollinger_width,
    "volatility.regime": compute_volatility_regime,
    "participation.rvol": compute_rvol,
    "participation.volume_trend": compute_volume_trend,
    "relative_strength.vs_benchmark": compute_rs_vs_benchmark,
    "relative_strength.regime": compute_rs_regime,
    "market_regime.breakout_state": compute_breakout_state,
    "market_regime.keltner_touch": compute_keltner_touch,
}


def warmup_bars_needed(
    readout_ids: list[str] | None = None,
) -> int:
    """Return the maximum ``lookback_bars`` across the given readouts (or all)."""
    ids = readout_ids or list(READOUTS)
    return max(READOUTS[rid].lookback_bars for rid in ids if rid in READOUTS)


def compute_all_readouts(
    bars: pl.DataFrame,
    indicators: pl.DataFrame | None,
    benchmark_bars: pl.DataFrame | None,
    as_of: datetime.datetime,
    profiles: dict[str, ThresholdProfile],
) -> list[ReadoutObservation]:
    """Compute all applicable readouts for a symbol.

    Only computes readouts whose ``source_requirements`` are satisfied by the
    provided data.
    """
    has_indicators = indicators is not None and not indicators.is_empty()
    has_benchmark = benchmark_bars is not None and not benchmark_bars.is_empty()

    ind_row = _build_indicator_dict(indicators) if has_indicators else None

    results: list[ReadoutObservation] = []
    for rid, defn in sorted(READOUTS.items()):
        reqs = defn.source_requirements
        if "technical_indicators" in reqs and not has_indicators:
            continue
        if "benchmark_bars" in reqs and not has_benchmark:
            continue
        if "bars_daily" not in reqs:
            continue

        if len(bars) < defn.lookback_bars:
            results.append(_make_obs(defn, None, "unavailable", as_of=as_of))
            continue

        prof_id = defn.threshold_profile_id or rid
        profile = profiles.get(prof_id)
        if profile is None:
            results.append(_make_obs(defn, None, "unavailable", as_of=as_of))
            continue

        computer = _READOUT_COMPUTERS.get(rid)
        if computer is None:
            results.append(_make_obs(defn, None, "unavailable", as_of=as_of))
            continue

        try:
            kwargs = {
                "bars": bars,
                "as_of": as_of,
                "definition": defn,
                "profile": profile,
            }
            sig = computer.__code__
            if "indicators" in sig.co_varnames:
                kwargs["indicators"] = ind_row
            if "benchmark_bars" in sig.co_varnames:
                kwargs["benchmark_bars"] = benchmark_bars
            obs = computer(**kwargs)
            results.append(obs)
        except Exception:
            results.append(_make_obs(defn, None, "unavailable", as_of=as_of))

    return results


def _build_indicator_dict(
    indicators: pl.DataFrame,
) -> dict[str, float | None]:
    """Build a flat dict of the most recent indicator values."""
    if indicators.is_empty():
        return {}
    last = indicators.row(-1, named=True)
    return {k: float(v) if v is not None else None for k, v in last.items()}


__all__ = [
    "ReadoutObservation",
    "compute_all_readouts",
    "warmup_bars_needed",
    "compute_daily_move",
    "compute_intraday_volatility",
    "compute_gap",
    "compute_trend_regime",
    "compute_directional_bias",
    "compute_trend_strength",
    "compute_rsi_14",
    "compute_macd_cross",
    "compute_momentum_quality",
    "compute_atr_percent",
    "compute_bollinger_width",
    "compute_volatility_regime",
    "compute_rvol",
    "compute_volume_trend",
    "compute_rs_vs_benchmark",
    "compute_rs_regime",
    "compute_breakout_state",
    "compute_keltner_touch",
]
