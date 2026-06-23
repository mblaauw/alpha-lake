from __future__ import annotations

import json

from alpha_lake.connectors.base import (
    RawFetch,
    build_client,
    build_manifest,
    check_budget,
    fetch_with_retry,
)
from alpha_lake.source_registry import get_source


async def fetch_attention(ticker: str, cohort: str = "all-stocks") -> RawFetch:
    cfg = get_source("apewisdom")
    check_budget(cfg)
    async with build_client(cfg) as client:
        endpoint = f"/filter/{cohort}/"
        response = await fetch_with_retry(client, endpoint, params={"page": 0})
        data = json.loads(response.content)
        results = data.get("results", [])
        total_pages = data.get("pages", 1)
        for page in range(1, total_pages):
            page_resp = await fetch_with_retry(client, endpoint, params={"page": page})
            results.extend(json.loads(page_resp.content).get("results", []))
        filtered = [r for r in results if r.get("ticker", "").upper() == ticker.upper()]
        seen: set[str] = set()
        deduped: list[dict] = []
        for r in filtered:
            key = r.get("ticker", "")
            if key and key not in seen:
                seen.add(key)
                deduped.append(r)
        body = json.dumps({"results": deduped}).encode()
        manifest = build_manifest(
            "apewisdom",
            endpoint,
            {"ticker": ticker, "cohort": cohort},
            body,
            200,
            1,
            key_mode="keyless",
        )
        return RawFetch(manifest=manifest, body=body)
