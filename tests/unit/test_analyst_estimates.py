from __future__ import annotations

from datetime import UTC, datetime

import polars as pl

from alpha_lake.canonical import DATASETS
from alpha_lake.models.analyst_estimate_fact import AnalystEstimateFact


def test_model_valid():
    df = pl.DataFrame(
        {
            "security_id": ["sec_abc"],
            "effective_date": ["2024-01-15"],
            "available_at": [datetime(2024, 1, 16, tzinfo=UTC)],
            "source_id": ["finnhub"],
            "strong_buy": [5],
            "buy": [8],
            "hold": [3],
            "sell": [1],
            "strong_sell": [0],
            "target_mean": [150.0],
            "target_high": [180.0],
            "target_low": [120.0],
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
    validated = AnalystEstimateFact.validate(df)
    assert len(validated) == 1


def test_registered():
    assert "analyst_estimates" in DATASETS
    ds = DATASETS["analyst_estimates"]
    assert ds.model is AnalystEstimateFact
    assert "security_id" in ds.natural_keys


def test_config(monkeypatch):
    monkeypatch.delenv("ALPHA_LAKE_CONFIG", raising=False)
    from alpha_lake.config import load_config

    cfg = load_config("config/stack.toml")
    assert "analyst_estimates" in cfg.datasets
    assert cfg.datasets["analyst_estimates"].tier == "experimental"
    assert cfg.quality["analyst_estimates"].max_staleness_days == 14
    assert "analyst_estimates" in cfg.precedence
    assert cfg.precedence["analyst_estimates"] == ["finnhub", "fmp"]
