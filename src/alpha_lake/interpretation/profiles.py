from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal

import polars as pl
from pydantic import BaseModel, Field


class ZoneDef(BaseModel):
    operator: Literal["lte", "gte", "between"]
    value: float | None = None
    min: float | None = None
    max: float | None = None


class PercentileDef(BaseModel):
    operator: Literal["lte", "gte", "between"]
    percentile: float | None = None
    min_percentile: float | None = None
    max_percentile: float | None = None


class ThresholdProfile(BaseModel):
    profile_id: str
    definition_id: str
    description: str
    version: str
    method: Literal["discrete", "percentile", "combined"]
    zones: dict[str, ZoneDef] = Field(default_factory=dict)
    percentiles: dict[str, PercentileDef] | None = None


def load_threshold_profiles(path: Path) -> dict[str, ThresholdProfile]:
    """Load versioned threshold profiles from a TOML file."""
    from alpha_lake.interpretation import READOUTS

    data = tomllib.loads(path.read_text())
    profiles: dict[str, ThresholdProfile] = {}

    profile_table = data.get("profile", {})
    for profile_id, raw in profile_table.items():
        profiles[profile_id] = ThresholdProfile(profile_id=profile_id, **raw)

    for pid, prof in profiles.items():
        if prof.definition_id not in READOUTS:
            msg = (
                f"Threshold profile {pid!r} references unknown definition_id {prof.definition_id!r}"
            )
            raise ValueError(msg)

    return profiles


def resolve_state(
    profile: ThresholdProfile,
    value: float | None,
    history: pl.Series | None = None,
    lookback_bars: int = 0,
) -> str:
    """Resolve a numeric value to a state string using the profile.

    For ``discrete`` profiles: direct zone lookup.
    For ``percentile`` profiles: compute percentile in *history* and match.
    For ``combined`` profiles: try discrete first, fall back to percentile.
    Returns ``"unavailable"`` when data is insufficient.
    """
    if value is None:
        return "unavailable"

    if history is not None and len(history) < lookback_bars:
        return "unavailable"

    if (
        (profile.method == "percentile" or profile.method == "combined")
        and profile.percentiles
        and history is not None
        and len(history) > 0
    ):
        clean = history.drop_nulls()
        if len(clean) > 0:
            pct = (clean < value).sum() / len(clean)
            for state, pdef in profile.percentiles.items():
                if _matches_percentile(pdef, float(pct)):
                    if profile.method == "percentile":
                        return state
                    if profile.method == "combined":
                        discrete_state = _match_zone(profile.zones, value)
                        if discrete_state:
                            return discrete_state
                        return state

    if profile.method == "discrete" or profile.method == "combined":
        result = _match_zone(profile.zones, value)
        if result:
            return result

    return "unavailable"


def _match_zone(zones: dict[str, ZoneDef], value: float) -> str | None:
    for state, zd in zones.items():
        if zd.operator == "lte":
            if value <= (zd.value if zd.value is not None else 0):
                return state
        elif zd.operator == "gte":
            if value >= (zd.value if zd.value is not None else 0):
                return state
        elif zd.operator == "between":
            lo = zd.min if zd.min is not None else float("-inf")
            hi = zd.max if zd.max is not None else float("inf")
            if lo <= value <= hi:
                return state
    return None


def _matches_percentile(pdef: PercentileDef, pct: float) -> bool:
    if pdef.operator == "lte":
        return pct <= (pdef.percentile if pdef.percentile is not None else 0)
    if pdef.operator == "gte":
        return pct >= (pdef.percentile if pdef.percentile is not None else 0)
    if pdef.operator == "between":
        lo = pdef.min_percentile if pdef.min_percentile is not None else 0.0
        hi = pdef.max_percentile if pdef.max_percentile is not None else 1.0
        return lo <= pct <= hi
    return False


__all__ = [
    "ThresholdProfile",
    "ZoneDef",
    "PercentileDef",
    "load_threshold_profiles",
    "resolve_state",
]
