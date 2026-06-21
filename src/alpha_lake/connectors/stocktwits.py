from __future__ import annotations

from alpha_lake.connectors.base import (
    RawFetch,
    build_client,
    build_manifest,
    check_budget,
    fetch_with_retry,
)
from alpha_lake.source_registry import get_source


async def fetch_sentiment(symbol: str, limit: int = 30) -> RawFetch:
    cfg = get_source("stocktwits")
    check_budget(cfg)
    params = {"limit": min(limit, 30)}
    async with build_client(cfg) as client:
        endpoint = f"/streams/symbol/{symbol}.json"
        response = await fetch_with_retry(client, endpoint, params=params)
        manifest = build_manifest(
            "stocktwits",
            endpoint,
            params,
            response.content,
            response.status_code,
            1,
            key_mode="keyless",
        )
        return RawFetch(manifest=manifest, body=response.content)
