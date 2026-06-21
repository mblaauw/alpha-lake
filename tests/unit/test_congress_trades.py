from __future__ import annotations

from datetime import UTC, datetime

import polars as pl

from alpha_lake.canonical import DATASETS
from alpha_lake.models.congress_trade_fact import CongressTradeFact


def test_model_valid():
    df = pl.DataFrame(
        {
            "transaction_id": ["tx_001"],
            "politician_id": ["pol_123"],
            "security_id": ["sec_abc"],
            "effective_date": ["2024-01-15"],
            "available_at": [datetime(2024, 1, 17, tzinfo=UTC)],
            "source_id": ["quiver"],
            "direction": ["buy"],
            "amount_range": ["1001-15000"],
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
    validated = CongressTradeFact.validate(df)
    assert len(validated) == 1


def test_registered():
    assert "congress_trades" in DATASETS
    ds = DATASETS["congress_trades"]
    assert ds.model is CongressTradeFact
    assert "transaction_id" in ds.natural_keys


def test_config(monkeypatch):
    monkeypatch.delenv("ALPHA_LAKE_CONFIG", raising=False)
    from alpha_lake.config import load_config

    cfg = load_config("config/stack.toml")
    assert "congress_trades" in cfg.datasets
    assert cfg.datasets["congress_trades"].tier == "experimental"
    assert cfg.quality["congress_trades"].max_staleness_days == 5
