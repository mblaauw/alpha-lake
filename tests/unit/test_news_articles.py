from __future__ import annotations

from datetime import UTC, datetime

import polars as pl

from alpha_lake.canonical import DATASETS
from alpha_lake.models.dataset_models import NewsArticleFact


def test_news_fact_valid():
    df = pl.DataFrame(
        {
            "article_id": ["finnhub_abc123"],
            "effective_date": ["2024-01-15"],
            "available_at": [datetime(2024, 1, 15, 12, 0, tzinfo=UTC)],
            "source_id": ["finnhub"],
            "title": ["Fed holds rates steady"],
            "description": ["The Fed kept rates unchanged."],
            "url": ["https://example.com/1"],
            "text_hash": ["abc"],
            "published_at": [datetime(2024, 1, 15, 10, 0, tzinfo=UTC)],
            "source_name": ["Finnhub"],
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
        pl.col("published_at").cast(pl.Datetime(time_zone="UTC")),
    )
    validated = NewsArticleFact.validate(df)
    assert len(validated) == 1


def test_news_registered():
    assert "news_articles" in DATASETS
    ds = DATASETS["news_articles"]
    assert ds.model is NewsArticleFact
    assert "article_id" in ds.natural_keys


def test_news_config(monkeypatch):
    monkeypatch.delenv("ALPHA_LAKE_CONFIG", raising=False)
    from alpha_lake.config import load_config

    cfg = load_config("config/stack.toml")
    assert "news_articles" in cfg.datasets
    assert cfg.datasets["news_articles"].tier == "experimental"
    assert "news" in cfg.precedence
    assert cfg.precedence["news"] == ["finnhub", "marketaux", "tiingo"]
