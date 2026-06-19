from __future__ import annotations

from alpha_lake.connectors.base import RawFetch, build_client, build_manifest, fetch_with_retry
from alpha_lake.source_registry import get_source


async def fetch_companyfacts(cik: str) -> RawFetch:
    """Fetch SEC EDGAR Companyfacts for a CIK number.

    Uses the modern SEC XBRL API at https://data.sec.gov/api/xbrl/companyfacts/CIK{padded}.json
    CIK must be zero-padded to 10 digits.
    """
    cfg = get_source("sec")
    cik_padded = cik.zfill(10)
    async with build_client(cfg) as client:
        endpoint = f"/api/xbrl/companyfacts/CIK{cik_padded}.json"
        response = await fetch_with_retry(client, endpoint)
        manifest = build_manifest("sec", endpoint, {}, response.content, response.status_code, 1)
        return RawFetch(manifest=manifest, body=response.content)
