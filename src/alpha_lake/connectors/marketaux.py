from __future__ import annotations

from typing import Any

from alpha_lake.connectors.base import RawFetch, build_client, build_manifest, fetch_with_retry
from alpha_lake.source_registry import get_source


async def fetch_news(symbol: str, from_date: str, to_date: str) -> RawFetch:
    cfg = get_source("marketaux")
    params: dict[str, Any] = {
        "api_token": cfg.api_key,
        "symbols": symbol,
        "published_after": from_date,
        "published_before": to_date,
        "limit": 50,
    }
    async with build_client(cfg) as client:
        endpoint = "/v1/news/all"
        response = await fetch_with_retry(client, endpoint, params=params)
        manifest = build_manifest(
            "marketaux",
            endpoint,
            params,
            response.content,
            response.status_code,
            1,
        )
        return RawFetch(manifest=manifest, body=response.content)
