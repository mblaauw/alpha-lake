from __future__ import annotations

from typing import Any

import httpx

from alpha_lake.connectors.base import RawFetch, build_manifest, check_budget
from alpha_lake.source_registry import get_source


async def fetch_earnings_calendar(from_date: str = "", to_date: str = "") -> RawFetch:
    cfg = get_source("finnhub")
    check_budget(cfg)
    params: dict[str, Any] = {"token": cfg.api_key}
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    headers = {}
    if cfg.contact_email:
        headers["User-Agent"] = f"alpha-lake/0.1.0 ({cfg.contact_email})"
    async with httpx.AsyncClient(base_url=cfg.base_url, headers=headers, timeout=30.0) as client:
        endpoint = "/calendar/earnings"
        response = await client.get(endpoint, params=params)
        manifest = build_manifest(
            "finnhub", endpoint, params, response.content, response.status_code, 1
        )
        return RawFetch(manifest=manifest, body=response.content)
