from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import polars as pl

from alpha_lake.calendar_ import shift_trading_days
from alpha_lake.config import get_config
from alpha_lake.interpretation import READOUTS
from alpha_lake.interpretation.profiles import load_threshold_profiles
from alpha_lake.interpretation.readouts import (
    compute_all_readouts,
    warmup_bars_needed,
)
from alpha_lake.security_master import resolve as resolve_security
from alpha_lake.serving import _pin_snapshot, read_bars_asof


def compute_readouts(
    con: duckdb.DuckDBPyConnection,
    symbol: str,
    as_of: datetime,
    *,
    snapshot_id: str | None = None,
    categories: str = "",
    readout_ids: str = "",
) -> dict[str, Any]:
    """Compute neutral readouts for *symbol* at *as_of*.

    Returns a dict matching the dashboard readout response shape:
    ``symbol``, ``as_of``, ``readouts``, ``metadata``.
    """
    if snapshot_id is not None:
        _pin_snapshot(con, snapshot_id)

    cfg = get_config()
    sec_id = resolve_security(con, symbol, as_of=as_of.date())
    if sec_id is None:
        sec_id = symbol

    warmup = warmup_bars_needed()
    start = shift_trading_days(as_of.date(), -warmup)

    bars_df = read_bars_asof(
        con,
        security_ids=[sec_id],
        as_of=as_of,
        start_date=start,
    )
    if bars_df.is_empty():
        return {
            "symbol": symbol,
            "as_of": as_of.isoformat(),
            "readouts": [],
            "metadata": {
                "computed_at": datetime.now(UTC).isoformat(),
                "bars_available": 0,
                "readouts_computed": 0,
                "readouts_unavailable": 0,
            },
        }
    bars_df = bars_df.sort("effective_date")

    indicators_df: pl.DataFrame | None = None
    with contextlib.suppress(Exception):
        indicators_df = con.execute(
            "SELECT * FROM technical_indicators"
            " WHERE security_id = ? AND available_at <= ?::TIMESTAMPTZ"
            " ORDER BY effective_date ASC",
            [sec_id, as_of],
        ).pl()

    benchmark = cfg.readouts.benchmark_symbol
    benchmark_df: pl.DataFrame | None = None
    if any("benchmark_bars" in r.source_requirements for r in READOUTS.values()):
        bm_id = resolve_security(con, benchmark, as_of=as_of.date())
        if bm_id is not None:
            with contextlib.suppress(Exception):
                benchmark_df = read_bars_asof(
                    con,
                    security_ids=[bm_id],
                    as_of=as_of,
                    start_date=start,
                )
                if not benchmark_df.is_empty():
                    benchmark_df = benchmark_df.sort("effective_date")

    profile_path = Path(cfg.readouts.profile_file)
    if not profile_path.exists():
        return {
            "symbol": symbol,
            "as_of": as_of.isoformat(),
            "readouts": [],
            "metadata": {
                "computed_at": datetime.now(UTC).isoformat(),
                "bars_available": len(bars_df),
                "readouts_computed": 0,
                "readouts_unavailable": 0,
                "error": f"Profile file not found: {profile_path}",
            },
        }
    profiles = load_threshold_profiles(profile_path)

    observations = compute_all_readouts(
        bars=bars_df,
        indicators=indicators_df,
        benchmark_bars=benchmark_df,
        as_of=as_of,
        profiles=profiles,
    )

    if categories:
        wanted_cats = {c.strip() for c in categories.split(",")}
        observations = [
            o
            for o in observations
            if (defn := READOUTS.get(o.definition_id)) is not None and defn.category in wanted_cats
        ]
    if readout_ids:
        wanted_ids = {r.strip() for r in readout_ids.split(",")}
        observations = [o for o in observations if o.definition_id in wanted_ids]

    readouts_json = []
    for obs in observations:
        defn = READOUTS.get(obs.definition_id)
        if defn is None:
            continue
        readouts_json.append(
            {
                "definition": {
                    "definition_id": defn.definition_id,
                    "name": defn.name,
                    "category": defn.category,
                    "source_requirements": defn.source_requirements,
                    "surface": defn.surface,
                    "description": defn.description,
                    "question": defn.question,
                    "calculation_formula": defn.calculation_formula,
                    "lookback_bars": defn.lookback_bars,
                    "parameters": defn.parameters,
                    "threshold_profile_id": defn.threshold_profile_id,
                    "display_value_type": defn.display_value_type,
                    "display_decimals": defn.display_decimals,
                    "display_suffix": defn.display_suffix,
                    "display_primary_label": defn.display_primary_label,
                    "display_secondary_label": defn.display_secondary_label,
                },
                "observation": obs.to_dict(),
            }
        )

    n_unavail = sum(1 for o in observations if o.state == "unavailable")
    return {
        "symbol": symbol,
        "as_of": as_of.isoformat(),
        "readouts": readouts_json,
        "metadata": {
            "computed_at": datetime.now(UTC).isoformat(),
            "bars_available": len(bars_df),
            "readouts_computed": len(observations),
            "readouts_unavailable": n_unavail,
        },
    }
