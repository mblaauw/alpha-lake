from __future__ import annotations

from typing import Any

from alpha_lake.connectors.base import RawFetch, build_client, build_manifest, fetch_with_retry
from alpha_lake.source_registry import get_source


async def fetch_bars_daily(
    symbol: str,
    from_date: str,
    to_date: str,
) -> RawFetch:
    cfg = get_source("tiingo")
    params: dict[str, Any] = {
        "startDate": from_date,
        "endDate": to_date,
        "token": cfg.api_key,
        "format": "json",
    }
    async with build_client(cfg) as client:
        endpoint = f"/tiingo/daily/{symbol}/prices"
        response = await fetch_with_retry(client, endpoint, params=params)
        raw_bytes = response.content
        manifest = build_manifest(
            source_id="tiingo",
            endpoint=endpoint,
            params=params,
            raw_bytes=raw_bytes,
            http_status=response.status_code,
            parser_version=1,
        )
        return RawFetch(manifest=manifest, body=raw_bytes)
