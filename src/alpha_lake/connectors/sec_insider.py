from __future__ import annotations

from alpha_lake.connectors.base import RawFetch, build_client, build_manifest, fetch_with_retry
from alpha_lake.source_registry import get_source


async def fetch_insider_transactions(cik: str, from_date: str = "", to_date: str = "") -> RawFetch:
    """Fetch SEC EDGAR insider filings (Forms 3/4/5) for a CIK.

    Uses the SEC EDGAR XBRL API. CIK must be zero-padded to 10 digits.
    """
    cfg = get_source("sec")
    cik_padded = cik.zfill(10)
    params: dict[str, str] = {}
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    async with build_client(cfg) as client:
        endpoint = f"/api/xbrl/insider/CIK{cik_padded}.json"
        response = await fetch_with_retry(client, endpoint, params=params or None)
        manifest = build_manifest("sec", endpoint, params, response.content, response.status_code, 1)
        return RawFetch(manifest=manifest, body=response.content)
