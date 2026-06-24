from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from alpha_lake.interpretation.profiles import (
    ThresholdProfile,
    load_threshold_profiles,
    resolve_state,
)


def _profile_toml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "test_profiles.toml"
    p.write_text(content)
    return p


def test_load_threshold_profiles_discrete(tmp_path: Path):
    toml = _profile_toml(
        tmp_path,
        """
[profile.daily_move_v1]
definition_id = "price_action.daily_move"
description = "Daily move thresholds"
version = "1.0.0"
method = "discrete"

[profile.daily_move_v1.zones]
up = { operator = "gte", value = 0.005 }
down = { operator = "lte", value = -0.005 }
flat = { operator = "between", min = -0.005, max = 0.005 }
""",
    )
    profiles = load_threshold_profiles(toml)
    assert "daily_move_v1" in profiles
    p = profiles["daily_move_v1"]
    assert p.method == "discrete"
    assert p.zones["up"].operator == "gte"
    assert p.zones["up"].value == 0.005


def test_load_threshold_profiles_percentile(tmp_path: Path):
    toml = _profile_toml(
        tmp_path,
        """
[profile.intraday_volatility_v1]
definition_id = "price_action.intraday_volatility"
description = "Intraday vol percentile thresholds"
version = "1.0.0"
method = "percentile"

[profile.intraday_volatility_v1.percentiles]
low = { operator = "lte", percentile = 0.1 }
normal = { operator = "between", min_percentile = 0.1, max_percentile = 0.9 }
elevated = { operator = "between", min_percentile = 0.9, max_percentile = 0.99 }
extreme = { operator = "gte", percentile = 0.99 }
""",
    )
    profiles = load_threshold_profiles(toml)
    assert "intraday_volatility_v1" in profiles
    p = profiles["intraday_volatility_v1"]
    assert p.method == "percentile"
    assert p.percentiles is not None


def test_load_profiles_unknown_definition_id_raises(tmp_path: Path):
    toml = _profile_toml(
        tmp_path,
        """
[profile.bogus]
definition_id = "nonexistent.readout"
description = "Bogus"
version = "1.0.0"
method = "discrete"
[profile.bogus.zones]
x = { operator = "gte", value = 0 }
""",
    )
    with pytest.raises(ValueError, match="unknown definition_id"):
        load_threshold_profiles(toml)


def test_resolve_state_discrete():
    from alpha_lake.interpretation.profiles import ZoneDef

    profile = ThresholdProfile(
        profile_id="test_v1",
        definition_id="price_action.daily_move",
        description="Test",
        version="1.0.0",
        method="discrete",
        zones={
            "up": ZoneDef(operator="gte", value=0.005),
            "down": ZoneDef(operator="lte", value=-0.005),
            "flat": ZoneDef(operator="between", min=-0.005, max=0.005),
        },
    )
    assert resolve_state(profile, 0.01) == "up"
    assert resolve_state(profile, -0.01) == "down"
    assert resolve_state(profile, 0.0) == "flat"
    assert resolve_state(profile, None) == "unavailable"


def test_resolve_state_percentile():
    from alpha_lake.interpretation.profiles import PercentileDef

    profile = ThresholdProfile(
        profile_id="test_pct_v1",
        definition_id="price_action.intraday_volatility",
        description="Test",
        version="1.0.0",
        method="percentile",
        percentiles={
            "low": PercentileDef(operator="lte", percentile=0.1),
            "normal": PercentileDef(operator="between", min_percentile=0.1, max_percentile=0.9),
            "elevated": PercentileDef(operator="between", min_percentile=0.9, max_percentile=0.99),
            "extreme": PercentileDef(operator="gte", percentile=0.99),
        },
    )
    history = pl.Series([0.005, 0.01, 0.015, 0.02, 0.025, 0.03, 0.035, 0.04, 0.045, 0.05])
    assert resolve_state(profile, 0.005, history, 10) == "low"
    assert resolve_state(profile, 0.02, history, 10) == "normal"


def test_resolve_state_percentile_insufficient_history():
    from alpha_lake.interpretation.profiles import PercentileDef

    profile = ThresholdProfile(
        profile_id="test_pct_v1",
        definition_id="price_action.intraday_volatility",
        description="Test",
        version="1.0.0",
        method="percentile",
        percentiles={
            "normal": PercentileDef(operator="between", min_percentile=0.0, max_percentile=1.0),
        },
    )
    history = pl.Series([0.01, 0.02])
    assert resolve_state(profile, 0.015, history, 10) == "unavailable"


def test_resolve_state_combined_discrete_first():
    from alpha_lake.interpretation.profiles import PercentileDef, ZoneDef

    profile = ThresholdProfile(
        profile_id="test_comb_v1",
        definition_id="volatility.bollinger_width",
        description="Test",
        version="1.0.0",
        method="combined",
        zones={
            "squeeze": ZoneDef(operator="lte", value=0.05),
        },
        percentiles={
            "expanding": PercentileDef(operator="gte", percentile=0.9),
        },
    )
    assert resolve_state(profile, 0.01) == "squeeze"


def test_resolve_state_combined_fallback_to_percentile():
    from alpha_lake.interpretation.profiles import PercentileDef, ZoneDef

    profile = ThresholdProfile(
        profile_id="test_comb_fb_v1",
        definition_id="volatility.bollinger_width",
        description="Test",
        version="1.0.0",
        method="combined",
        zones={
            "squeeze": ZoneDef(operator="lte", value=0.05),
        },
        percentiles={
            "expanding": PercentileDef(operator="gte", percentile=0.9),
        },
    )
    history = pl.Series([0.1, 0.15, 0.2, 0.25, 0.28] + [0.3] * 16)
    assert resolve_state(profile, 1.0, history, 21) == "expanding"


def test_resolve_state_no_match_returns_unavailable():
    from alpha_lake.interpretation.profiles import ZoneDef

    profile = ThresholdProfile(
        profile_id="test_no_v1",
        definition_id="price_action.daily_move",
        description="Test",
        version="1.0.0",
        method="discrete",
        zones={
            "up": ZoneDef(operator="gte", value=100),
        },
    )
    assert resolve_state(profile, 0.5) == "unavailable"


def test_load_actual_profiles():
    path = Path("config/threshold_profiles.toml")
    profiles = load_threshold_profiles(path)
    assert len(profiles) >= 18
    assert all(p.version == "1.0.0" for p in profiles.values())
