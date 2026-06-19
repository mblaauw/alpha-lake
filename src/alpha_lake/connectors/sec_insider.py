from __future__ import annotations

from alpha_lake.connectors.base import RawFetch, build_client, build_manifest, fetch_with_retry
from alpha_lake.source_registry import get_source


async def fetch_insider_transactions(cik: str, from_date: str = "", to_date: str = "") -> RawFetch:
    """Fetch SEC EDGAR insider filings (Forms 3/4/5) for a CIK.

    Uses the SEC EDGAR full-text search for insider filings.
    CIK must be zero-padded to 10 digits.
    """
    cfg = get_source("sec")
    cik_padded = cik.zfill(10)
    params: dict[str, str] = {
        "cik": cik_padded,
        "type": "3,4,5",
        "dateb": to_date or "",
        "datea": from_date or "",
    }
    async with build_client(cfg) as client:
        endpoint = "/cgi-bin/browse-edgar"
        response = await fetch_with_retry(client, endpoint, params=params)
        manifest = build_manifest("sec", endpoint, params, response.content, response.status_code, 1)
        return RawFetch(manifest=manifest, body=response.content)
