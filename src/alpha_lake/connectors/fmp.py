"""Financial Modeling Prep connector.

Note: Both analyst-estimates and economic-calendar endpoints require a paid
FMP subscription. Free-tier keys will receive 402/403 responses.
"""

from __future__ import annotations

from typing import Any

from alpha_lake.connectors.base import (
    RawFetch,
    build_client,
    build_manifest,
    check_budget,
    fetch_with_retry,
)
from alpha_lake.source_registry import get_source


async def fetch_analyst_ratings(symbol: str) -> RawFetch:
    cfg = get_source("fmp")
    check_budget(cfg)
    params: dict[str, Any] = {
        "apikey": cfg.api_key,
        "symbol": symbol,
    }
    async with build_client(cfg) as client:
        endpoint = "/analyst-estimates"
        response = await fetch_with_retry(client, endpoint, params=params)
        manifest = build_manifest(
            "fmp",
            endpoint,
            params,
            response.content,
            response.status_code,
            1,
        )
        return RawFetch(manifest=manifest, body=response.content)


async def fetch_economic_calendar(
    from_date: str = "",
    to_date: str = "",
) -> RawFetch:
    """Fetch economic calendar events from Financial Modeling Prep.

    Uses the keyed endpoint at ``/economic-calendar`` with ``apikey``
    as a query parameter. Returns a single ``RawFetch`` with the full
    window; callers should use ``fetch_windowed()`` for large ranges.

    Note: Requires a paid FMP subscription. Free-tier keys return 402.
    """
    cfg = get_source("fmp")
    check_budget(cfg)

    params: dict[str, Any] = {
        "apikey": cfg.api_key,
    }
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date

    async with build_client(cfg) as client:
        endpoint = "/economic-calendar"
        response = await fetch_with_retry(client, endpoint, params=params)
        manifest = build_manifest(
            "fmp",
            endpoint,
            params,
            response.content,
            response.status_code,
            1,
        )
        return RawFetch(manifest=manifest, body=response.content)
