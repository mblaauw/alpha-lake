from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from alpha_lake.fixtures import (
    _generate_analyst_estimates,
    _generate_earnings_calendar,
    _generate_fundamental_facts,
)
from alpha_lake.harness import EmbeddedHarness
from alpha_lake.replay import check_replay

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "fundamentals"


def test_fundamentals_golden_replay():
    from datetime import UTC, datetime

    from alpha_lake.derived.fundamental_metrics import (
        compute_estimate_metrics,
        compute_fundamental_period_metrics,
    )

    if not _FIXTURE_DIR.exists():
        pytest.skip("golden fixture not found; run `just freeze-fixtures` first")

    harness = EmbeddedHarness()
    harness.start()

    as_of = datetime(2025, 12, 31, 23, 59, 0, tzinfo=UTC)

    facts = _generate_fundamental_facts()
    period_metrics = compute_fundamental_period_metrics(facts, as_of, ingestion_run_id="r1")

    estimates = _generate_analyst_estimates()
    earnings = _generate_earnings_calendar()
    est_metrics = compute_estimate_metrics(estimates, earnings, as_of, ingestion_run_id="r1")

    parts = [p for p in [period_metrics, est_metrics] if not p.is_empty()]
    result = pl.concat(parts) if parts else period_metrics

    assert check_replay(_FIXTURE_DIR, result), (
        "fundamentals golden replay mismatch — maybe regenerate with `just freeze-fixtures`."
    )
    harness.stop()
