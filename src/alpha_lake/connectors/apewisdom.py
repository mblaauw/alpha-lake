from __future__ import annotations

from alpha_lake.connectors.base import (
    RawFetch,
    build_client,
    build_manifest,
    check_budget,
    fetch_with_retry,
)
from alpha_lake.source_registry import get_source


async def fetch_attention(ticker: str) -> RawFetch:
    cfg = get_source("apewisdom")
    check_budget(cfg)
    async with build_client(cfg) as client:
        endpoint = f"/filter/ticker/{ticker}/"
        response = await fetch_with_retry(client, endpoint)
        manifest = build_manifest(
            "apewisdom",
            endpoint,
            None,
            response.content,
            response.status_code,
            1,
            key_mode="keyless",
        )
        return RawFetch(manifest=manifest, body=response.content)
