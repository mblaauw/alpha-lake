import asyncio
import hashlib
import json
from pathlib import Path

import polars as pl

from alpha_lake.replay import load_golden_hash

_FIXTURE_DIR = Path(__file__).parent / "replay" / "fixtures"


def golden_hash() -> str:
    return load_golden_hash(_FIXTURE_DIR)


def sample_bars_df() -> pl.DataFrame:
    from datetime import date, datetime

    df = pl.DataFrame(
        {
            "security_id": ["sec_aap"],
            "effective_date": [date(2026, 1, 5)],
            "available_at": [datetime(2026, 1, 5, 16, 0, 0)],
            "source_id": ["eodhd"],
            "open": [200.0],
            "high": [205.0],
            "low": [199.0],
            "close": [203.5],
            "volume": [5000000],
            "source_fetch_id": ["f1"],
            "raw_payload_hash": ["h1"],
            "ingestion_run_id": ["r1"],
            "content_hash": ["c1"],
            "version_hash": [""],
            "schema_version": [1],
            "parser_version": [1],
            "quality_status": ["valid"],
            "source_published_at": [None],
            "ingested_at": [None],
            "validated_at": [None],
        }
    ).with_columns(
        pl.col("source_published_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("ingested_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("validated_at").cast(pl.Datetime(time_zone="UTC")),
    )
    return df


def sample_bars_restated() -> pl.DataFrame:
    from datetime import date, datetime

    df = pl.DataFrame(
        {
            "security_id": ["sec_aap"],
            "effective_date": [date(2026, 1, 5)],
            "available_at": [datetime(2026, 1, 6, 8, 0, 0)],
            "source_id": ["eodhd"],
            "open": [201.0],
            "high": [206.0],
            "low": [198.0],
            "close": [204.0],
            "volume": [5100000],
            "source_fetch_id": ["f2"],
            "raw_payload_hash": ["h2"],
            "ingestion_run_id": ["r2"],
            "content_hash": ["c2"],
            "version_hash": [""],
            "schema_version": [1],
            "parser_version": [1],
            "quality_status": ["valid"],
            "source_published_at": [None],
            "ingested_at": [None],
            "validated_at": [None],
        }
    ).with_columns(
        pl.col("source_published_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("ingested_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("validated_at").cast(pl.Datetime(time_zone="UTC")),
    )
    return df


_LIVE_DIR = Path(__file__).parent / "fixtures" / "live"


def _cache_key(**kwargs: str | None) -> str:
    parts = [f"{k}={v}" for k, v in sorted(kwargs.items()) if v]
    raw = "_".join(parts) if parts else "default"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def cached_fetch(source: str, dataset: str, **kwargs: str | None) -> bytes:
    from alpha_lake.config import load_config
    from alpha_lake.connectors import get_connector

    load_config()
    key = _cache_key(**kwargs)
    cache_path = _LIVE_DIR / source / dataset / f"{key}.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    if cache_path.exists():
        return cache_path.read_bytes()

    connector = get_connector(source, dataset)
    if connector is None:
        raise ValueError(f"No connector registered for {source}/{dataset}")
    raw_fetch = asyncio.run(connector(**{k: v for k, v in kwargs.items() if v}))
    cache_path.write_bytes(raw_fetch.body)
    return raw_fetch.body


def cached_normalize(
    source: str,
    dataset: str,
    extract_key: str | None = None,
    series_id: str | None = None,
    security_id: str | None = None,
    **fetch_kwargs: str | None,
) -> pl.DataFrame:

    from alpha_lake.clock import get_clock

    raw_body = cached_fetch(source, dataset, **fetch_kwargs)
    raw_data = json.loads(raw_body)

    records: list[dict]
    if extract_key and isinstance(raw_data, dict):
        records = raw_data.get(extract_key, [raw_data])
    elif isinstance(raw_data, list):
        records = raw_data
    else:
        records = [raw_data]

    clock_now = get_clock().now()
    run_id = f"test_{clock_now.strftime('%Y%m%d_%H%M%S')}"
    content_hash = hashlib.sha256(raw_body).hexdigest()

    if dataset == "macro_series":
        from alpha_lake.normalize import macro_series_from_json

        return macro_series_from_json(
            raw=records,
            series_id=series_id or "GDP",
            source_id=source,
            source_fetch_id=f"fetch_{run_id}",
            ingestion_run_id=run_id,
            content_hash=content_hash,
            available_at=clock_now,
        )

    if dataset == "economic_calendar":
        from alpha_lake.normalize import economic_calendar_from_json

        return economic_calendar_from_json(
            raw=records,
            source_id=source,
            source_fetch_id=f"fetch_{run_id}",
            ingestion_run_id=run_id,
            content_hash=content_hash,
            available_at=clock_now,
        )

    if dataset == "sentiment" and source == "stocktwits":
        from alpha_lake.normalize import stocktwits_sentiment_from_json

        return stocktwits_sentiment_from_json(
            raw=records,
            symbol=security_id or "AAPL",
            source_id=source,
            source_fetch_id=f"fetch_{run_id}",
            ingestion_run_id=run_id,
            content_hash=content_hash,
            available_at=clock_now,
        )

    if dataset == "sentiment" and source == "marketaux":
        from alpha_lake.normalize import marketaux_sentiment_from_json

        return marketaux_sentiment_from_json(
            raw=records,
            source_id=source,
            source_fetch_id=f"fetch_{run_id}",
            ingestion_run_id=run_id,
            content_hash=content_hash,
            available_at=clock_now,
        )

    if dataset == "sentiment":
        from alpha_lake.normalize import sentiment_from_news

        return sentiment_from_news(
            raw=records,
            source_id=source,
            source_fetch_id=f"fetch_{run_id}",
            ingestion_run_id=run_id,
            content_hash=content_hash,
            available_at=clock_now,
        )

    if dataset == "news" and source == "marketaux":
        from alpha_lake.normalize import marketaux_news_from_json

        return marketaux_news_from_json(
            raw=records,
            source_id=source,
            source_fetch_id=f"fetch_{run_id}",
            ingestion_run_id=run_id,
            content_hash=content_hash,
            available_at=clock_now,
        )

    if dataset == "news":
        from alpha_lake.normalize import news_from_json

        return news_from_json(
            raw=records,
            source_id=source,
            source_fetch_id=f"fetch_{run_id}",
            ingestion_run_id=run_id,
            content_hash=content_hash,
            available_at=clock_now,
        )

    if dataset == "analyst_estimates":
        from alpha_lake.normalize import analyst_estimates_from_json

        return analyst_estimates_from_json(
            raw=records,
            security_id=security_id or "AAPL",
            source_id=source,
            source_fetch_id=f"fetch_{run_id}",
            ingestion_run_id=run_id,
            content_hash=content_hash,
            available_at=clock_now,
        )

    if dataset == "insider_tx":
        from alpha_lake.normalize import insider_tx_from_json

        return insider_tx_from_json(
            raw=records,
            security_id=security_id or "AAPL",
            source_id=source,
            source_fetch_id=f"fetch_{run_id}",
            ingestion_run_id=run_id,
            content_hash=content_hash,
            available_at=clock_now,
        )

    if dataset == "attention_metrics":
        from alpha_lake.normalize import apewisdom_attention_from_json

        return apewisdom_attention_from_json(
            raw=records,
            ticker=security_id or "AAPL",
            source_id=source,
            source_fetch_id=f"fetch_{run_id}",
            ingestion_run_id=run_id,
            content_hash=content_hash,
            available_at=clock_now,
        )

    msg = f"No normalize path wired for {source}/{dataset}"
    raise ValueError(msg)
