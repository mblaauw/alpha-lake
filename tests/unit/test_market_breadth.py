from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import polars as pl

from alpha_lake.canonical import DATASETS
from alpha_lake.derived.market_breadth import compute_market_breadth
from alpha_lake.models.market_breadth_fact import MarketBreadthFact


def _sample_bars(count: int = 252) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "security_id": ["sec_a"] * count,
            "effective_date": [(date(2024, 1, 1) + timedelta(days=i)) for i in range(count)],
            "close": [100.0 + i * 0.5 for i in range(count)],
            "available_at": [datetime(2024, 1, 1, tzinfo=UTC)] * count,
        }
    )


def test_model_valid():
    df = pl.DataFrame(
        {
            "metric_id": ["pct_above_50ma"],
            "effective_date": ["2024-01-15"],
            "available_at": [datetime(2024, 1, 16, tzinfo=UTC)],
            "value": [75.0],
            "source_id": ["derived"],
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
    validated = MarketBreadthFact.validate(df)
    assert len(validated) == 1


def test_registered():
    assert "market_breadth" in DATASETS
    ds = DATASETS["market_breadth"]
    assert ds.model is MarketBreadthFact
    assert "metric_id" in ds.natural_keys


def test_empty_bars():
    bars = pl.DataFrame(
        schema={
            "security_id": pl.String,
            "effective_date": pl.Date,
            "close": pl.Float64,
            "available_at": pl.Datetime(time_zone="UTC"),
        }
    )
    result = compute_market_breadth(bars, as_of=datetime(2024, 1, 10, tzinfo=UTC))
    assert result.is_empty()


def test_ma_pct_single_sector():
    bars = _sample_bars(252)
    result = compute_market_breadth(
        bars,
        as_of=datetime(2024, 1, 10, tzinfo=UTC),
        basket_ids=["sec_a"],
    )
    assert not result.is_empty()
    pct_50ma = result.filter(pl.col("metric_id") == "pct_above_50ma")
    assert len(pct_50ma) > 0


def test_ratio_pair():
    bars_a = _sample_bars(30)
    bars_b = _sample_bars(30).with_columns(pl.lit("sec_b").alias("security_id"))
    bars = pl.concat([bars_a, bars_b])
    result = compute_market_breadth(
        bars,
        as_of=datetime(2024, 1, 10, tzinfo=UTC),
        ratio_pairs=[("SPY_QQQ", "sec_a", "sec_b")],
    )
    ratio_rows = result.filter(pl.col("metric_id").str.starts_with("ratio"))
    assert len(ratio_rows) > 0


def test_config(monkeypatch):
    monkeypatch.delenv("ALPHA_LAKE_CONFIG", raising=False)
    from alpha_lake.config import load_config

    cfg = load_config("config/stack.toml")
    assert "market_breadth" in cfg.datasets
    assert cfg.datasets["market_breadth"].tier == "experimental"
    assert cfg.quality["market_breadth"].max_staleness_days == 2
