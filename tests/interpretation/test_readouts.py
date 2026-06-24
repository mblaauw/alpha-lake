from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import polars as pl
import pytest

from alpha_lake.interpretation import READOUTS, ReadoutDefinition
from alpha_lake.interpretation.profiles import (
    ThresholdProfile,
    load_threshold_profiles,
)
from alpha_lake.interpretation.readouts import (
    ReadoutObservation,
    compute_all_readouts,
    compute_atr_percent,
    compute_bollinger_width,
    compute_breakout_state,
    compute_daily_move,
    compute_directional_bias,
    compute_gap,
    compute_intraday_volatility,
    compute_keltner_touch,
    compute_macd_cross,
    compute_momentum_quality,
    compute_rs_regime,
    compute_rs_vs_benchmark,
    compute_rsi_14,
    compute_rvol,
    compute_trend_regime,
    compute_trend_strength,
    compute_volatility_regime,
    compute_volume_trend,
    warmup_bars_needed,
)

_AS_OF = datetime(2026, 6, 1, 16, 0, tzinfo=UTC)
_START = date(2026, 1, 1)


def _bars(
    closes: list[float], highs: list[float] | None = None, lows: list[float] | None = None
) -> pl.DataFrame:
    n = len(closes)
    opens = [c * 1.001 for c in closes]
    vols = [1_000_000] * n
    dates = [_START + timedelta(days=i) for i in range(n)]
    return pl.DataFrame(
        {
            "effective_date": dates,
            "open": opens,
            "high": highs or [c * 1.02 for c in closes],
            "low": lows or [c * 0.98 for c in closes],
            "close": closes,
            "volume": vols,
            "security_id": ["sec_a"] * n,
            "available_at": [_AS_OF] * n,
        }
    ).with_columns(
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
    )


def _discrete_profile(defn: ReadoutDefinition) -> ThresholdProfile:
    from alpha_lake.interpretation.profiles import ZoneDef

    return ThresholdProfile(
        profile_id=defn.threshold_profile_id,
        definition_id=defn.definition_id,
        description="Test",
        version="1.0.0",
        method="discrete",
        zones={
            "constructive": ZoneDef(operator="gte", value=0.01),
            "weak": ZoneDef(operator="lte", value=-0.01),
            "neutral": ZoneDef(operator="between", min=-0.01, max=0.01),
        },
    )


def _make_profile(defn: ReadoutDefinition) -> ThresholdProfile:
    from pathlib import Path

    profiles = load_threshold_profiles(Path("config/threshold_profiles.toml"))
    pid = defn.threshold_profile_id
    return profiles.get(pid) or _discrete_profile(defn)


def _load_all_profiles():
    from pathlib import Path

    return load_threshold_profiles(Path("config/threshold_profiles.toml"))


# --- Price Action ---


def test_daily_move_up():
    defn = READOUTS["price_action.daily_move"]
    bars = _bars([100.0, 102.0])
    obs = compute_daily_move(bars, _AS_OF, defn, _discrete_profile(defn))
    assert obs.definition_id == "price_action.daily_move"
    assert obs.value is not None and obs.value > 0
    assert obs.state != "unavailable"
    assert obs.orientation == "upward"


def test_daily_move_down():
    defn = READOUTS["price_action.daily_move"]
    bars = _bars([100.0, 98.0])
    obs = compute_daily_move(bars, _AS_OF, defn, _discrete_profile(defn))
    assert obs.value is not None and obs.value < 0
    assert obs.orientation == "downward"


def test_daily_move_unavailable_single_bar():
    defn = READOUTS["price_action.daily_move"]
    bars = _bars([100.0])
    obs = compute_daily_move(bars, _AS_OF, defn, _discrete_profile(defn))
    assert obs.state == "unavailable"
    assert obs.value is None


def test_intraday_volatility_normal():
    defn = READOUTS["price_action.intraday_volatility"]
    bars = _bars([100.0, 101.0], highs=[102.0, 103.0], lows=[98.0, 99.0])
    obs = compute_intraday_volatility(bars, _AS_OF, defn, _make_profile(defn))
    assert obs.definition_id == "price_action.intraday_volatility"
    assert obs.state != "unavailable"
    assert obs.value is not None


def test_intraday_volatility_zero_close():
    defn = READOUTS["price_action.intraday_volatility"]
    bars = pl.DataFrame(
        {
            "effective_date": [_START, _START + timedelta(days=1)],
            "open": [100.0, 99.0],
            "high": [102.0, 101.0],
            "low": [98.0, 97.0],
            "close": [100.0, 0.0],
            "volume": [1_000_000, 1_000_000],
            "security_id": ["sec_a", "sec_a"],
            "available_at": [_AS_OF, _AS_OF],
        }
    ).with_columns(pl.col("available_at").cast(pl.Datetime(time_zone="UTC")))
    obs = compute_intraday_volatility(bars, _AS_OF, defn, _discrete_profile(defn))
    assert obs.state == "unavailable"


def test_gap_up():
    defn = READOUTS["price_action.gap"]
    bars = _bars([100.0, 105.0])
    obs = compute_gap(bars, _AS_OF, defn, _discrete_profile(defn))
    assert obs.definition_id == "price_action.gap"
    assert obs.value is not None and obs.value > 0
    assert obs.orientation == "upward"


def test_gap_unavailable_single_bar():
    defn = READOUTS["price_action.gap"]
    bars = _bars([100.0])
    obs = compute_gap(bars, _AS_OF, defn, _discrete_profile(defn))
    assert obs.state == "unavailable"


# --- Trend ---


def test_trend_regime():
    defn = READOUTS["trend.regime"]
    bars = _bars([100.0 + i * 0.5 for i in range(30)])
    obs = compute_trend_regime(bars, _AS_OF, defn, _make_profile(defn))
    assert obs.definition_id == "trend.regime"
    assert obs.state != "unavailable"
    assert obs.value is not None


def test_trend_regime_with_indicators():
    defn = READOUTS["trend.regime"]
    bars = _bars([100.0 + i * 0.5 for i in range(30)])
    obs = compute_trend_regime(
        bars,
        _AS_OF,
        defn,
        _make_profile(defn),
        indicators={"adx_14": 45.0},
    )
    assert obs.state != "unavailable"
    assert obs.value == 45.0


def test_trend_regime_unavailable_short_bars():
    defn = READOUTS["trend.regime"]
    bars = _bars([100.0, 101.0])
    obs = compute_trend_regime(bars, _AS_OF, defn, _make_profile(defn))
    assert isinstance(obs, ReadoutObservation)


def test_directional_bias():
    defn = READOUTS["trend.directional_bias"]
    bars = _bars([100.0 + i * 0.5 for i in range(30)])
    obs = compute_directional_bias(bars, _AS_OF, defn, _make_profile(defn))
    assert obs.definition_id == "trend.directional_bias"
    assert obs.state != "unavailable"
    assert obs.orientation in ("upward", "downward", "mixed")


def test_trend_strength():
    defn = READOUTS["trend.strength"]
    bars = _bars([100.0 + i * 0.5 for i in range(30)])
    obs = compute_trend_strength(bars, _AS_OF, defn, _make_profile(defn))
    assert obs.state != "unavailable"
    assert obs.value is not None


# --- Momentum ---


def test_rsi_14():
    defn = READOUTS["momentum.rsi_14"]
    bars = _bars([100.0 + i * 2.0 for i in range(30)])
    obs = compute_rsi_14(bars, _AS_OF, defn, _make_profile(defn))
    assert obs.definition_id == "momentum.rsi_14"
    assert obs.state != "unavailable"
    assert 0 <= (obs.value or 0) <= 100


def test_rsi_14_orientation():
    defn = READOUTS["momentum.rsi_14"]
    bars = _bars([100.0 + i * 2.0 for i in range(30)])
    obs = compute_rsi_14(bars, _AS_OF, defn, _make_profile(defn))
    assert obs.orientation in ("upward", "downward", "mixed", "not_applicable")


def test_macd_cross():
    defn = READOUTS["momentum.macd_cross"]
    bars = _bars([100.0 + i * 1.5 for i in range(40)])
    obs = compute_macd_cross(bars, _AS_OF, defn, _make_profile(defn))
    assert obs.definition_id == "momentum.macd_cross"
    assert obs.state != "unavailable"
    assert obs.orientation is not None


def test_momentum_quality():
    defn = READOUTS["momentum.quality"]
    bars = _bars([100.0 + i * 0.5 for i in range(30)])
    obs = compute_momentum_quality(bars, _AS_OF, defn, _make_profile(defn))
    assert obs.definition_id == "momentum.quality"
    assert obs.state != "unavailable"


def test_momentum_quality_unavailable_short():
    defn = READOUTS["momentum.quality"]
    bars = _bars([100.0, 101.0])
    obs = compute_momentum_quality(bars, _AS_OF, defn, _make_profile(defn))
    assert obs.state == "unavailable"


# --- Volatility ---


def test_atr_percent():
    defn = READOUTS["volatility.atr_percent"]
    bars = _bars([100.0] * 260, highs=[102.0] * 260, lows=[98.0] * 260)
    obs = compute_atr_percent(bars, _AS_OF, defn, _make_profile(defn))
    assert obs.definition_id == "volatility.atr_percent"
    assert obs.state != "unavailable"
    assert obs.value is not None


def test_atr_percent_unavailable_short():
    defn = READOUTS["volatility.atr_percent"]
    bars = _bars([100.0, 101.0])
    obs = compute_atr_percent(bars, _AS_OF, defn, _make_profile(defn))
    assert obs.state == "unavailable"


def test_bollinger_width():
    defn = READOUTS["volatility.bollinger_width"]
    bars = _bars([100.0] * 50 + [110.0] * 50 + [90.0] * 50)
    obs = compute_bollinger_width(bars, _AS_OF, defn, _make_profile(defn))
    assert obs.definition_id == "volatility.bollinger_width"
    assert obs.state != "unavailable"


def test_volatility_regime():
    defn = READOUTS["volatility.regime"]
    bars = _bars(
        [100.0] * 30 + [100.0 + i * 0.5 for i in range(40)],
        highs=[102.0] * 70,
        lows=[98.0] * 70,
    )
    obs = compute_volatility_regime(bars, _AS_OF, defn, _make_profile(defn))
    assert obs.definition_id == "volatility.regime"
    assert obs.state != "unavailable"


# --- Participation ---


def test_rvol():
    defn = READOUTS["participation.rvol"]
    bars = _bars([100.0] * 30)
    obs = compute_rvol(bars, _AS_OF, defn, _make_profile(defn))
    assert obs.definition_id == "participation.rvol"
    assert obs.state != "unavailable"


def test_volume_trend():
    defn = READOUTS["participation.volume_trend"]
    bars = _bars([100.0] * 10)
    obs = compute_volume_trend(bars, _AS_OF, defn, _make_profile(defn))
    assert obs.definition_id == "participation.volume_trend"
    assert obs.state != "unavailable"


def test_volume_trend_unavailable_short():
    defn = READOUTS["participation.volume_trend"]
    bars = _bars([100.0, 101.0, 102.0])
    obs = compute_volume_trend(bars, _AS_OF, defn, _make_profile(defn))
    assert obs.state == "unavailable"


# --- Relative Strength ---


def test_rs_vs_benchmark():
    defn = READOUTS["relative_strength.vs_benchmark"]
    bars = _bars([100.0 + i * 0.5 for i in range(30)])
    bm_bars = _bars([100.0 + i * 0.3 for i in range(30)])
    obs = compute_rs_vs_benchmark(bars, _AS_OF, defn, _make_profile(defn), benchmark_bars=bm_bars)
    assert obs.definition_id == "relative_strength.vs_benchmark"
    assert obs.state != "unavailable"
    assert obs.value is not None


def test_rs_vs_benchmark_unavailable_no_benchmark():
    defn = READOUTS["relative_strength.vs_benchmark"]
    bars = _bars([100.0 + i * 0.5 for i in range(30)])
    obs = compute_rs_vs_benchmark(bars, _AS_OF, defn, _make_profile(defn), benchmark_bars=None)
    assert obs.state == "unavailable"


def test_rs_regime():
    defn = READOUTS["relative_strength.regime"]
    bars = _bars([100.0 + i * 0.5 for i in range(30)])
    bm_bars = _bars([100.0 + i * 0.3 for i in range(30)])
    obs = compute_rs_regime(bars, _AS_OF, defn, _make_profile(defn), benchmark_bars=bm_bars)
    assert obs.definition_id == "relative_strength.regime"
    assert obs.state != "unavailable"


# --- Market Regime ---


def test_breakout_state():
    defn = READOUTS["market_regime.breakout_state"]
    bars = _bars([100.0] * 10 + list(range(100, 120)))
    obs = compute_breakout_state(bars, _AS_OF, defn, _make_profile(defn))
    assert obs.definition_id == "market_regime.breakout_state"
    assert obs.state != "unavailable"


def test_breakout_state_unavailable_short():
    defn = READOUTS["market_regime.breakout_state"]
    bars = _bars([100.0, 101.0])
    obs = compute_breakout_state(bars, _AS_OF, defn, _make_profile(defn))
    assert obs.state == "unavailable"


def test_keltner_touch():
    defn = READOUTS["market_regime.keltner_touch"]
    bars = _bars([100.0] * 40, highs=[102.0] * 40, lows=[98.0] * 40)
    obs = compute_keltner_touch(bars, _AS_OF, defn, _make_profile(defn))
    assert obs.definition_id == "market_regime.keltner_touch"
    assert obs.state != "unavailable"
    assert obs.orientation in ("upward", "downward", "mixed")


# --- Orchestrator ---


def test_compute_all_readouts_no_indicators():
    bars = _bars([100.0, 102.0])
    profiles = _load_all_profiles()
    obs_list = compute_all_readouts(
        bars, indicators=None, benchmark_bars=None, as_of=_AS_OF, profiles=profiles
    )
    assert len(obs_list) > 0
    for obs in obs_list:
        assert isinstance(obs, ReadoutObservation)
        assert obs.as_of == _AS_OF


def test_compute_all_readouts_with_indicators():
    bars = _bars([100.0] * 40)
    profiles = _load_all_profiles()
    ind = pl.DataFrame({"rsi_14": [55.0], "adx_14": [25.0]})
    bm = _bars([100.0] * 40)
    obs_list = compute_all_readouts(
        bars, indicators=ind, benchmark_bars=bm, as_of=_AS_OF, profiles=profiles
    )
    assert len(obs_list) > 0


def test_compute_all_readouts_insufficient_bars():
    bars = _bars([100.0, 101.0])
    profiles = _load_all_profiles()
    obs_list = compute_all_readouts(
        bars, indicators=None, benchmark_bars=None, as_of=_AS_OF, profiles=profiles
    )
    long_ids = {rid for rid, d in READOUTS.items() if d.lookback_bars > 2}
    for obs in obs_list:
        if obs.definition_id in long_ids:
            assert obs.state == "unavailable", (
                f"{obs.definition_id} should be unavailable with 2 bars"
            )


def test_compute_all_readouts_no_indicators_skips_technical():
    bars = _bars([100.0] * 40)
    profiles = _load_all_profiles()
    obs_list = compute_all_readouts(
        bars, indicators=None, benchmark_bars=None, as_of=_AS_OF, profiles=profiles
    )
    tech_ids = {
        rid for rid, d in READOUTS.items() if "technical_indicators" in d.source_requirements
    }
    obs_ids = {o.definition_id for o in obs_list}
    assert not tech_ids.intersection(obs_ids)


def test_compute_all_readouts_no_benchmark_skips_rs():
    bars = _bars([100.0] * 40)
    profiles = _load_all_profiles()
    obs_list = compute_all_readouts(
        bars, indicators=None, benchmark_bars=None, as_of=_AS_OF, profiles=profiles
    )
    rs_ids = {rid for rid, d in READOUTS.items() if "benchmark_bars" in d.source_requirements}
    obs_ids = {o.definition_id for o in obs_list}
    assert not rs_ids.intersection(obs_ids)


def test_warmup_bars_needed():
    n = warmup_bars_needed()
    assert n > 0
    assert n >= 253


def test_warmup_bars_needed_subset():
    n = warmup_bars_needed(readout_ids=["price_action.daily_move"])
    assert n == 2


# --- ReadoutObservation ---


def test_observation_to_dict():
    obs = ReadoutObservation(
        definition_id="test.readout",
        value=0.015,
        state="constructive",
        orientation="upward",
        attention="normal",
        risk="normal",
        data_confidence="high",
        color="green",
        as_of=_AS_OF,
    )
    d = obs.to_dict()
    assert d["definition_id"] == "test.readout"
    assert d["value"] == 0.015
    assert d["state"] == "constructive"
    assert d["as_of"] == _AS_OF.isoformat()


def test_observation_to_dict_none_value():
    obs = ReadoutObservation(
        definition_id="test.readout",
        value=None,
        state="unavailable",
        orientation="not_applicable",
        attention="normal",
        risk="normal",
        data_confidence="low",
        color="gray",
        as_of=_AS_OF,
    )
    d = obs.to_dict()
    assert d["value"] is None
    assert d["state"] == "unavailable"


# --- Determinism ---


def test_readout_determinism():
    defn = READOUTS["price_action.daily_move"]
    bars = _bars([100.0, 102.0])
    prof = _discrete_profile(defn)
    obs1 = compute_daily_move(bars, _AS_OF, defn, prof)
    obs2 = compute_daily_move(bars, _AS_OF, defn, prof)
    assert obs1.value == obs2.value
    assert obs1.state == obs2.state
    assert obs1.orientation == obs2.orientation


def test_all_readouts_deterministic():
    bars = _bars([100.0] * 40)
    profiles = _load_all_profiles()
    ind = pl.DataFrame({"rsi_14": [55.0], "adx_14": [25.0]})
    bm = _bars([100.0] * 40)
    r1 = compute_all_readouts(bars, ind, bm, _AS_OF, profiles)
    r2 = compute_all_readouts(bars, ind, bm, _AS_OF, profiles)
    for o1, o2 in zip(r1, r2, strict=True):
        assert o1.value == o2.value, f"Mismatch for {o1.definition_id}"
        assert o1.state == o2.state, f"Mismatch for {o1.definition_id}"


def test_observation_frozen():
    obs = ReadoutObservation(
        definition_id="test.r",
        value=1.0,
        state="good",
        orientation="upward",
        attention="normal",
        risk="normal",
        data_confidence="high",
        color="green",
        as_of=_AS_OF,
    )
    with pytest.raises(AttributeError):
        ReadoutObservation.__setattr__(obs, "state", "bad")
