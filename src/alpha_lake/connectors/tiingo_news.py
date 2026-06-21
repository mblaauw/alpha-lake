from __future__ import annotations

from typing import Any

from alpha_lake.connectors.base import RawFetch, build_client, build_manifest, fetch_with_retry
from alpha_lake.source_registry import get_source


async def fetch_news(tickers: list[str], start_date: str, end_date: str) -> RawFetch:
    cfg = get_source("tiingo")
    params: dict[str, Any] = {
        "token": cfg.api_key,
        "startDate": start_date,
        "endDate": end_date,
        "tickers": ",".join(tickers),
        "sort": "date",
    }
    async with build_client(cfg) as client:
        endpoint = "/tiingo/news"
        response = await fetch_with_retry(client, endpoint, params=params)
        manifest = build_manifest(
            "tiingo",
            endpoint,
            params,
            response.content,
            response.status_code,
            1,
        )
        return RawFetch(manifest=manifest, body=response.content)
