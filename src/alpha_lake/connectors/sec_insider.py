from __future__ import annotations

from typing import Any

from alpha_lake.connectors.base import RawFetch, build_client, build_manifest, fetch_with_retry
from alpha_lake.source_registry import get_source


async def fetch_insider_transactions(cik: str, from_date: str = "", to_date: str = "") -> RawFetch:
    cfg = get_source("sec")
    params: dict[str, str] = {}
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    async with build_client(cfg) as client:
        endpoint = f"/cgi-bin/own-disp?action=getissuer&CIK={cik}"
        response = await fetch_with_retry(client, endpoint, params=params or None)
        manifest = build_manifest("sec", endpoint, params, response.content, response.status_code, 1)
        return RawFetch(manifest=manifest, body=response.content)
