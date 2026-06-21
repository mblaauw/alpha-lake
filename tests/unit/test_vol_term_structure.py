from __future__ import annotations

from datetime import UTC, date, datetime

import polars as pl
import pytest

from alpha_lake.canonical import DATASETS
from alpha_lake.derived.vol_term_structure import compute_vol_term_structure
from alpha_lake.models.vol_term_structure_fact import VolTermStructureFact


def test_model_valid():
    df = pl.DataFrame(
        {
            "series_id": ["VIX"],
            "effective_date": ["2024-01-15"],
            "available_at": [datetime(2024, 1, 16, tzinfo=UTC)],
            "source_id": ["derived"],
            "value": [15.5],
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
    validated = VolTermStructureFact.validate(df)
    assert len(validated) == 1


def test_registered():
    assert "vol_term_structure" in DATASETS
    ds = DATASETS["vol_term_structure"]
    assert ds.model is VolTermStructureFact
    assert "series_id" in ds.natural_keys


def _bar(series_id: str, close: float, dt: date) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "security_id": [series_id],
            "effective_date": [dt],
            "close": [close],
            "available_at": [datetime(2024, 1, 1, tzinfo=UTC)],
        }
    )


def test_compute_levels():
    dt = date(2024, 1, 15)
    bars = pl.concat(
        [
            _bar("VIX", 15.0, dt),
            _bar("VIX9D", 14.0, dt),
            _bar("VIX3M", 18.0, dt),
            _bar("VIX6M", 20.0, dt),
        ]
    )
    result = compute_vol_term_structure(bars, as_of=datetime(2024, 1, 15, tzinfo=UTC))
    assert not result.is_empty()
    vix_rows = result.filter(pl.col("series_id") == "VIX")
    assert vix_rows["value"][0] == 15.0


def test_compute_contango_spread():
    dt = date(2024, 1, 15)
    bars = pl.concat(
        [
            _bar("VIX", 15.0, dt),
            _bar("VIX9D", 14.0, dt),
            _bar("VIX3M", 18.0, dt),
            _bar("VIX6M", 20.0, dt),
        ]
    )
    result = compute_vol_term_structure(bars, as_of=datetime(2024, 1, 15, tzinfo=UTC))
    spread = result.filter(pl.col("series_id") == "contango_3m_spot")
    assert len(spread) == 1
    assert spread["value"][0] == 18.0 - 15.0  # 3.0


def test_compute_ratio():
    dt = date(2024, 1, 15)
    bars = pl.concat(
        [
            _bar("VIX", 15.0, dt),
            _bar("VIX9D", 14.0, dt),
            _bar("VIX3M", 18.0, dt),
        ]
    )
    result = compute_vol_term_structure(bars, as_of=datetime(2024, 1, 15, tzinfo=UTC))
    ratio = result.filter(pl.col("series_id") == "contango_front_ratio")
    assert len(ratio) == 1
    assert ratio["value"][0] == pytest.approx(14.0 / 15.0)


def test_empty_bars():
    bars = pl.DataFrame(
        schema={
            "security_id": pl.String,
            "effective_date": pl.Date,
            "close": pl.Float64,
            "available_at": pl.Datetime(time_zone="UTC"),
        }
    )
    result = compute_vol_term_structure(bars, as_of=datetime(2024, 1, 15, tzinfo=UTC))
    assert result.is_empty()


def test_config(monkeypatch):
    monkeypatch.delenv("ALPHA_LAKE_CONFIG", raising=False)
    from alpha_lake.config import load_config

    cfg = load_config("config/stack.toml")
    assert "vol_term_structure" in cfg.datasets
    assert cfg.datasets["vol_term_structure"].tier == "experimental"
    assert cfg.quality["vol_term_structure"].max_staleness_days == 2
