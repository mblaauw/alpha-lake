from __future__ import annotations

from typing import Any

from alpha_lake.connectors.base import RawFetch, build_client, build_manifest, fetch_with_retry
from alpha_lake.source_registry import get_source


async def fetch_splits(symbol: str) -> RawFetch:
    cfg = get_source("eodhd")
    params: dict[str, Any] = {"api_token": cfg.api_key}
    async with build_client(cfg) as client:
        endpoint = f"/splits/{symbol}.US"
        response = await fetch_with_retry(client, endpoint, params=params)
        manifest = build_manifest(
            "eodhd",
            endpoint,
            params,
            response.content,
            response.status_code,
            1,
        )
        return RawFetch(manifest=manifest, body=response.content)


async def fetch_dividends(symbol: str, from_date: str, to_date: str) -> RawFetch:
    cfg = get_source("eodhd")
    params: dict[str, Any] = {"from": from_date, "to": to_date, "api_token": cfg.api_key}
    async with build_client(cfg) as client:
        endpoint = f"/div/{symbol}.US"
        response = await fetch_with_retry(client, endpoint, params=params)
        manifest = build_manifest(
            "eodhd",
            endpoint,
            params,
            response.content,
            response.status_code,
            1,
        )
        return RawFetch(manifest=manifest, body=response.content)
