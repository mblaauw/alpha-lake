from __future__ import annotations

from pathlib import Path

import polars as pl

from alpha_lake.canonical import write_bars
from alpha_lake.harness import EmbeddedHarness
from alpha_lake.replay import freeze_output
from alpha_lake.serving import read_bars_asof

_FIXTURE_DIR = Path(__file__).parents[3] / "tests" / "replay" / "fixtures"


def _sample_bars() -> pl.DataFrame:
    from datetime import date, datetime

    return pl.DataFrame({
        "security_id": ["sec_aap"], "effective_date": [date(2026, 1, 5)],
        "available_at": [datetime(2026, 1, 5, 16, 0, 0)],
        "source_id": ["eodhd"], "open": [200.0], "high": [205.0], "low": [199.0], "close": [203.5],
        "volume": [5000000], "source_fetch_id": ["f1"], "raw_payload_hash": ["h1"],
        "ingestion_run_id": ["r1"], "content_hash": ["c1"], "version_hash": [""],
        "schema_version": [1], "parser_version": [1], "quality_status": ["valid"],
        "source_published_at": [None], "ingested_at": [None], "validated_at": [None],
    }).with_columns(
        pl.col("source_published_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("ingested_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("validated_at").cast(pl.Datetime(time_zone="UTC")),
    )


def freeze() -> None:
    from datetime import datetime

    harness = EmbeddedHarness()
    harness.start()

    bars = _sample_bars()
    write_bars(harness.conn, bars)

    pit_result = read_bars_asof(
        harness.conn,
        ["sec_aap"],
        datetime(2026, 1, 5, 17, 0, 0),
    )

    _FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    freeze_output(pit_result, _FIXTURE_DIR)

    harness.stop()
    print(f"Froze {len(bars)} bars -> {_FIXTURE_DIR}")
