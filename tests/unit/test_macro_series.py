from __future__ import annotations

from datetime import UTC, datetime

import polars as pl

from alpha_lake.canonical import DATASETS, compute_version_hash
from alpha_lake.models.macro_fact import MacroSeriesFact
from alpha_lake.normalize import macro_series_from_json

UTC = UTC


def test_macro_fact_valid():
    df = pl.DataFrame(
        {
            "series_id": ["CPIAUCSL"],
            "effective_date": ["2024-01-01"],
            "available_at": [datetime(2024, 1, 10, tzinfo=UTC)],
            "source_id": ["fred"],
            "value": [100.5],
            "source_fetch_id": ["fetch_abc"],
            "raw_payload_hash": ["hash1"],
            "ingestion_run_id": ["run1"],
            "content_hash": ["hash1"],
            "version_hash": [""],
            "schema_version": [1],
            "parser_version": [1],
            "quality_status": ["valid"],
        }
    ).with_columns(
        pl.col("effective_date").str.to_date("%Y-%m-%d"),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
    )
    validated = MacroSeriesFact.validate(df)
    assert len(validated) == 1


def test_macro_fact_negative_value():
    """Negative values are allowed in macro series (e.g. GDP contraction)."""
    df = pl.DataFrame(
        {
            "series_id": ["GDP"],
            "effective_date": ["2020-06-30"],
            "available_at": [datetime(2020, 7, 30, tzinfo=UTC)],
            "source_id": ["fred"],
            "value": [-31.4],
            "source_fetch_id": ["fetch_def"],
            "raw_payload_hash": ["hash2"],
            "ingestion_run_id": ["run1"],
            "content_hash": ["hash2"],
            "version_hash": [""],
            "schema_version": [1],
            "parser_version": [1],
            "quality_status": ["valid"],
        }
    ).with_columns(
        pl.col("effective_date").str.to_date("%Y-%m-%d"),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
    )
    validated = MacroSeriesFact.validate(df)
    assert len(validated) == 1


def test_macro_series_has_dataset_registry_entry():
    assert "macro_series" in DATASETS
    ds = DATASETS["macro_series"]
    assert ds.table == "macro_series"
    assert ds.model is MacroSeriesFact
    assert "series_id" in ds.natural_keys
    assert "effective_date" in ds.natural_keys
    assert "source_id" in ds.natural_keys


def test_normalize_macro_series():
    raw = [
        {"date": "2024-01-01", "value": "100.5"},
        {"date": "2024-01-02", "value": "101.2"},
    ]
    df = macro_series_from_json(
        raw=raw,
        series_id="CPIAUCSL",
        source_id="fred",
        source_fetch_id="fetch1",
        ingestion_run_id="run1",
        content_hash="ch1",
        available_at=datetime(2024, 1, 10, 12, 0, tzinfo=UTC),
    )
    assert len(df) == 2
    assert df["series_id"][0] == "CPIAUCSL"
    assert df["value"][0] == 100.5
    assert df["value"][1] == 101.2
    assert str(df["effective_date"][0]) == "2024-01-01"


def test_normalize_macro_series_skips_empty_values():
    """FRED returns '.' for missing values; these should be filtered."""
    raw = [
        {"date": "2024-01-01", "value": "100.5"},
        {"date": "2024-01-02", "value": "."},
        {"date": "2024-01-03", "value": ""},
    ]
    df = macro_series_from_json(
        raw=raw,
        series_id="UNRATE",
        source_id="fred",
        source_fetch_id="fetch1",
        ingestion_run_id="run1",
        content_hash="ch1",
        available_at=datetime(2024, 1, 10, 12, 0, tzinfo=UTC),
    )
    assert len(df) == 1  # only the valid row survives
    assert df["value"][0] == 100.5


def test_version_hash_macro_series():
    raw = [
        {"date": "2024-01-01", "value": "100.5"},
    ]
    df = macro_series_from_json(
        raw=raw,
        series_id="CPIAUCSL",
        source_id="fred",
        source_fetch_id="fetch1",
        ingestion_run_id="run1",
        content_hash="ch1",
        available_at=datetime(2024, 1, 10, 12, 0, tzinfo=UTC),
    )
    df = compute_version_hash(df)
    assert len(df["version_hash"][0]) == 64  # sha256 hex
    assert df["normalization_version"][0] == 1


def test_macro_series_stack_config(monkeypatch):
    """macro_series appears in stack.toml config."""
    monkeypatch.delenv("ALPHA_LAKE_CONFIG", raising=False)
    from alpha_lake.config import load_config

    cfg = load_config("config/stack.toml")
    assert "macro_series" in cfg.datasets
    assert cfg.datasets["macro_series"].tier == "experimental"
    assert cfg.datasets["macro_series"].supported is False
    assert "macro_series" in cfg.quality
    assert cfg.quality["macro_series"].max_staleness_days == 45
