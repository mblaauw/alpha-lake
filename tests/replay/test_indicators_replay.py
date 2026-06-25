from __future__ import annotations

from pathlib import Path

import pytest

from alpha_lake.fixtures import _generate_indicator_bars
from alpha_lake.harness import EmbeddedHarness
from alpha_lake.replay import check_replay

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "indicators"


def test_indicator_golden_replay():
    from datetime import UTC, datetime

    from alpha_lake.canonical import write_bars
    from alpha_lake.derived.compute import compute_all_indicators
    from alpha_lake.serving import read_bars_asof

    if not _FIXTURE_DIR.exists():
        pytest.skip("golden fixture not found; run `just freeze-fixtures` first")

    harness = EmbeddedHarness()
    harness.start()

    bars = _generate_indicator_bars()
    write_bars(harness.conn, bars)

    as_of = datetime(2026, 1, 5, 17, 0, 0, tzinfo=UTC)
    bars_df = read_bars_asof(harness.conn, ["sec_aap", "sec_msft"], as_of)

    result = compute_all_indicators(bars_df, as_of)
    if "version_hash" in result.columns:
        result = result.sort(["security_id", "effective_date"])

    assert check_replay(_FIXTURE_DIR, result), (
        "indicator golden replay mismatch — maybe regenerate with `just freeze-fixtures`."
    )
    harness.stop()
