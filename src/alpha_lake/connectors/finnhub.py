from __future__ import annotations

from typing import Any

import httpx

from alpha_lake.connectors.base import (
    RawFetch,
    build_manifest,
    check_budget,
    fetch_with_retry,
)
from alpha_lake.source_registry import get_source


def _build_finnhub_client(cfg) -> httpx.AsyncClient:
    headers = {}
    if cfg.contact_email:
        headers["User-Agent"] = f"alpha-lake/0.1.0 ({cfg.contact_email})"
    return httpx.AsyncClient(
        base_url=cfg.base_url,
        headers=headers,
        timeout=30.0,
    )


async def fetch_insider_sentiment(symbol: str) -> RawFetch:
    cfg = get_source("finnhub")
    check_budget(cfg)
    params: dict[str, Any] = {
        "token": cfg.api_key,
        "symbol": symbol,
    }
    async with _build_finnhub_client(cfg) as client:
        endpoint = "/stock/insider-sentiment"
        response = await fetch_with_retry(client, endpoint, params=params)
        manifest = build_manifest(
            "finnhub",
            endpoint,
            params,
            response.content,
            response.status_code,
            1,
        )
        return RawFetch(manifest=manifest, body=response.content)


async def fetch_recommendation_trends(symbol: str) -> RawFetch:
    cfg = get_source("finnhub")
    check_budget(cfg)
    params: dict[str, Any] = {
        "token": cfg.api_key,
        "symbol": symbol,
    }
    async with _build_finnhub_client(cfg) as client:
        endpoint = "/stock/recommendation-trends"
        response = await fetch_with_retry(client, endpoint, params=params)
        manifest = build_manifest(
            "finnhub",
            endpoint,
            params,
            response.content,
            response.status_code,
            1,
        )
        return RawFetch(manifest=manifest, body=response.content)


async def fetch_news(symbol: str, from_date: str, to_date: str) -> RawFetch:
    cfg = get_source("finnhub")
    params: dict[str, Any] = {
        "token": cfg.api_key,
        "symbol": symbol,
        "from": from_date,
        "to": to_date,
    }
    async with _build_finnhub_client(cfg) as client:
        endpoint = "/company-news"
        response = await fetch_with_retry(client, endpoint, params=params)
        manifest = build_manifest(
            "finnhub",
            endpoint,
            params,
            response.content,
            response.status_code,
            1,
        )
        return RawFetch(manifest=manifest, body=response.content)
