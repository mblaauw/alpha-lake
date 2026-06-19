from __future__ import annotations

from typing import Any

import httpx

from alpha_lake.connectors.base import RawFetch, build_manifest
from alpha_lake.source_registry import get_source


async def _get_oauth_token(cfg) -> str:
    """Get Reddit OAuth2 token via client credentials flow."""
    import os
    client_id = os.environ.get("REDDIT_CLIENT_ID", "")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET", "")
    auth = httpx.BasicAuth(client_id, client_secret)
    async with httpx.AsyncClient() as client:
        r = await client.post("https://www.reddit.com/api/v1/access_token",
            auth=auth, data={"grant_type": "client_credentials"},
            headers={"User-Agent": "alpha-lake/0.1"})
        r.raise_for_status()
        return r.json()["access_token"]


async def fetch_subreddit(subreddit: str, limit: int = 100) -> RawFetch:
    cfg = get_source("reddit")
    token = await _get_oauth_token(cfg)
    headers = {
        "User-Agent": "alpha-lake/0.1 (market-data lakehouse)",
        "Authorization": f"Bearer {token}",
    }
    async with httpx.AsyncClient(base_url=cfg.base_url, headers=headers, timeout=30.0) as client:
        endpoint = f"/r/{subreddit}/hot.json"
        params: dict[str, Any] = {"limit": min(limit, 100)}
        response = await client.get(endpoint, params=params)
        raw_bytes = response.content
        manifest = build_manifest("reddit", endpoint, params, raw_bytes, response.status_code, 1)
        return RawFetch(manifest=manifest, body=raw_bytes)
