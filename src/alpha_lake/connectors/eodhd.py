from __future__ import annotations

from typing import Any

from alpha_lake.connectors.base import RawFetch, build_client, build_manifest, compute_content_hash, fetch_with_retry
from alpha_lake.source_registry import get_source


async def fetch_bars_daily(
    symbol: str,
    from_date: str,
    to_date: str,
) -> RawFetch:
    cfg = get_source("eodhd")
    params: dict[str, Any] = {
        "from": from_date,
        "to": to_date,
        "period": "d",
        "api_token": cfg.api_key,
    }
    async with build_client(cfg) as client:
        endpoint = f"/eod/{symbol}.US"
        response = await fetch_with_retry(client, endpoint, params=params)
        raw_bytes = response.content
        manifest = build_manifest(
            source_id="eodhd",
            endpoint=endpoint,
            params=params,
            raw_bytes=raw_bytes,
            http_status=response.status_code,
            parser_version=1,
        )
        return RawFetch(manifest=manifest, body=raw_bytes)
