from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from alpha_lake.fixtures import _generate_indicator_bars, _generate_spy_bars
from alpha_lake.harness import EmbeddedHarness
from alpha_lake.replay import check_replay

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "readouts"
_PROFILES_PATH = Path(__file__).parent / ".." / ".." / "config" / "threshold_profiles.toml"


def test_readouts_golden_replay():
    from datetime import UTC, datetime

    from alpha_lake.canonical import write_bars
    from alpha_lake.interpretation.profiles import load_threshold_profiles
    from alpha_lake.interpretation.readouts import compute_all_readouts
    from alpha_lake.serving import read_bars_asof

    if not _FIXTURE_DIR.exists():
        pytest.skip("golden fixture not found; run `just freeze-fixtures` first")

    harness = EmbeddedHarness()
    harness.start()

    bars = _generate_indicator_bars()
    write_bars(harness.conn, bars)
    spy = _generate_spy_bars()
    write_bars(harness.conn, spy)

    as_of = datetime(2026, 1, 5, 17, 0, 0, tzinfo=UTC)
    bars_df = read_bars_asof(harness.conn, ["sec_aap", "sec_msft"], as_of)
    spy_df = read_bars_asof(harness.conn, ["SPY"], as_of)

    profiles = load_threshold_profiles(_PROFILES_PATH)
    observations = compute_all_readouts(bars_df, None, spy_df, as_of, profiles)

    obs_dicts = [o.to_dict() for o in observations]
    df = pl.DataFrame(obs_dicts)

    assert check_replay(_FIXTURE_DIR, df), (
        "readouts golden replay mismatch — maybe regenerate with `just freeze-fixtures`."
    )
    harness.stop()
