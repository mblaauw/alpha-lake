from __future__ import annotations

from datetime import UTC, date, datetime

import polars as pl
import pytest

from alpha_lake.canonical import DATASETS
from alpha_lake.derived.relative_strength import _RS_WINDOWS, compute_relative_strength
from alpha_lake.models.relative_strength_fact import RelativeStrengthFact


def test_model_valid():
    df = pl.DataFrame(
        {
            "security_id": ["sec_abc"],
            "effective_date": ["2024-01-15"],
            "available_at": [datetime(2024, 1, 16, tzinfo=UTC)],
            "window": [21],
            "source_id": ["derived"],
            "rs_return": [0.05],
            "rs_percentile": [75.0],
            "source_fetch_id": [""],
            "raw_payload_hash": [""],
            "ingestion_run_id": [""],
            "content_hash": [""],
            "version_hash": [""],
            "schema_version": [1],
            "parser_version": [1],
            "quality_status": ["valid"],
        }
    ).with_columns(
        pl.col("effective_date").str.to_date("%Y-%m-%d"),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
    )
    validated = RelativeStrengthFact.validate(df)
    assert len(validated) == 1


def test_registered():
    assert "relative_strength" in DATASETS
    ds = DATASETS["relative_strength"]
    assert ds.model is RelativeStrengthFact
    assert "window" in ds.natural_keys


def test_rs_windows_defined():
    assert 1 in _RS_WINDOWS
    assert 252 in _RS_WINDOWS
    assert len(_RS_WINDOWS) == 6


def _make_bars(sid: str, closes: list[float]) -> pl.DataFrame:
    dates = [f"2024-01-{i + 1:02d}" for i in range(len(closes))]
    return pl.DataFrame(
        {
            "security_id": [sid] * len(closes),
            "effective_date": dates,
            "close": closes,
            "available_at": [datetime(2024, 1, 1, tzinfo=UTC)] * len(closes),
        }
    ).with_columns(pl.col("effective_date").str.to_date("%Y-%m-%d"))


def test_rs_returns_difference():
    bars = _make_bars("sec_a", [100.0, 105.0, 110.0])
    benchmark = _make_bars("SPY", [100.0, 102.0, 104.0])
    result = compute_relative_strength(bars, benchmark, as_of=datetime(2024, 1, 3, tzinfo=UTC))
    assert not result.is_empty()
    rs_1d = result.filter(pl.col("window") == 1, pl.col("effective_date") == date(2024, 1, 2))
    assert len(rs_1d) == 1
    expected_rs = (105 / 100 - 1) - (102 / 100 - 1)
    assert rs_1d["rs_return"][0] == pytest.approx(expected_rs)


def test_rs_empty_when_no_data():
    bars = pl.DataFrame(
        schema={
            "security_id": pl.String,
            "effective_date": pl.Date,
            "close": pl.Float64,
            "available_at": pl.Datetime(time_zone="UTC"),
        }
    )
    benchmark = _make_bars("SPY", [100.0])
    result = compute_relative_strength(bars, benchmark, as_of=datetime(2024, 1, 3, tzinfo=UTC))
    assert result.is_empty()


def test_rs_percentile_with_universe():
    bars_a = _make_bars("sec_a", [100.0, 110.0, 120.0])
    bars_b = _make_bars("sec_b", [100.0, 105.0, 108.0])
    bars = pl.concat([bars_a, bars_b])
    benchmark = _make_bars("SPY", [100.0, 101.0, 102.0])
    result = compute_relative_strength(
        bars,
        benchmark,
        as_of=datetime(2024, 1, 3, tzinfo=UTC),
        universe_ids=["sec_a", "sec_b"],
    )
    rs_percentiles = result.filter(pl.col("window") == 1)["rs_percentile"].drop_nulls()
    assert len(rs_percentiles) > 0
    max_val = rs_percentiles.max()
    min_val = rs_percentiles.min()
    assert max_val is not None and min_val is not None


def test_rs_config(monkeypatch):
    monkeypatch.delenv("ALPHA_LAKE_CONFIG", raising=False)
    from alpha_lake.config import load_config

    cfg = load_config("config/stack.toml")
    assert "relative_strength" in cfg.datasets
    assert cfg.datasets["relative_strength"].tier == "experimental"
    assert cfg.quality["relative_strength"].max_staleness_days == 2
