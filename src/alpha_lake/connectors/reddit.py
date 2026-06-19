from __future__ import annotations

from typing import Any

import httpx

from alpha_lake.connectors.base import RawFetch, build_manifest
from alpha_lake.source_registry import get_source


async def fetch_subreddit(subreddit: str, limit: int = 100) -> RawFetch:
    cfg = get_source("reddit")
    headers = {"User-Agent": "alpha-lake/0.1 (market-data lakehouse)"}
    async with httpx.AsyncClient(base_url=cfg.base_url, headers=headers, timeout=30.0) as client:
        endpoint = f"/r/{subreddit}/hot.json"
        params: dict[str, Any] = {"limit": min(limit, 100)}
        response = await client.get(endpoint, params=params)
        raw_bytes = response.content
        manifest = build_manifest("reddit", endpoint, params, raw_bytes, response.status_code, 1)
        return RawFetch(manifest=manifest, body=raw_bytes)
