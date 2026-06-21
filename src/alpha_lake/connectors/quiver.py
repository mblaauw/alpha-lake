from __future__ import annotations

from alpha_lake.connectors.base import (
    RawFetch,
    build_client,
    build_manifest,
    check_budget,
    fetch_with_retry,
)
from alpha_lake.source_registry import get_source


async def fetch_congress_trades() -> RawFetch:
    cfg = get_source("quiver")
    check_budget(cfg)
    params = {"apikey": cfg.api_key}
    async with build_client(cfg) as client:
        endpoint = "/live/congresstrading"
        response = await fetch_with_retry(client, endpoint, params=params)
        manifest = build_manifest(
            "quiver",
            endpoint,
            params,
            response.content,
            response.status_code,
            1,
        )
        return RawFetch(manifest=manifest, body=response.content)
