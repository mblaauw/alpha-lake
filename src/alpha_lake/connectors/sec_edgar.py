from __future__ import annotations

from typing import Any

from alpha_lake.connectors.base import RawFetch, build_client, build_manifest, fetch_with_retry
from alpha_lake.source_registry import get_source


async def fetch_companyfacts(cik: str) -> RawFetch:
    """Fetch SEC EDGAR Companyfacts for a CIK number."""
    cfg = get_source("sec")
    async with build_client(cfg) as client:
        endpoint = f"/cgi-bin/own?action=getcompany&CIK={cik}&type=text&start=0&count=100"
        response = await fetch_with_retry(client, endpoint)
        manifest = build_manifest("sec", endpoint, {}, response.content, response.status_code, 1)
        return RawFetch(manifest=manifest, body=response.content)
