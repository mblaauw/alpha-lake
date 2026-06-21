from __future__ import annotations

from typing import Any

from alpha_lake.connectors.alpaca_base import alpaca_client
from alpha_lake.connectors.base import RawFetch, build_manifest


async def fetch_daily_bars(symbol: str, start: str, end: str) -> RawFetch:
    params: dict[str, Any] = {"symbols": symbol, "start": start, "end": end, "timeframe": "1Day"}
    async with alpaca_client() as client:
        endpoint = "/v2/stocks/bars"
        response = await client.get(endpoint, params=params)
        manifest = build_manifest(
            "alpaca",
            endpoint,
            params,
            response.content,
            response.status_code,
            1,
        )
        return RawFetch(manifest=manifest, body=response.content)
