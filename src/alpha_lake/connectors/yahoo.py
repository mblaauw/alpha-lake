from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from alpha_lake.connectors.base import RawFetch, build_client, build_manifest, fetch_with_retry
from alpha_lake.source_registry import get_source

log = logging.getLogger("alpha_lake")


def _to_unix(d: str) -> int:
    return int(datetime.fromisoformat(d).replace(tzinfo=UTC).timestamp())


def _to_iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d")


async def fetch_bars_daily(
    symbol: str,
    from_date: str,
    to_date: str,
) -> RawFetch:
    cfg = get_source("yahoo")
    period1 = _to_unix(from_date)
    period2 = _to_unix(to_date) + 86400
    params: dict[str, Any] = {
        "period1": period1,
        "period2": period2,
        "interval": "1d",
    }
    async with build_client(cfg) as client:
        endpoint = f"/v8/finance/chart/{symbol}"
        # Yahoo blocks the default httpx User-Agent from container IPs
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
        response = await client.get(endpoint, params=params, headers=headers)
        raw_bytes = response.content

        rows: list[dict[str, Any]] = []
        if response.status_code == 200 and raw_bytes:
            try:
                raw_data = json.loads(raw_bytes)
                result = raw_data.get("chart", {}).get("result", [None])[0]
                if result:
                    timestamps = result.get("timestamp") or []
                    quotes = result.get("indicators", {}).get("quote", [{}])[0] or {}
                    for i, ts in enumerate(timestamps):
                        rows.append(
                            {
                                "date": _to_iso(ts),
                                "open": quotes.get("open", [None])[i],
                                "high": quotes.get("high", [None])[i],
                                "low": quotes.get("low", [None])[i],
                                "close": quotes.get("close", [None])[i],
                                "volume": quotes.get("volume", [None])[i],
                            }
                        )
            except json.JSONDecodeError:
                log.warning("Yahoo returned non-JSON for %s: HTTP %d", symbol, response.status_code)

        transformed = json.dumps(rows).encode()

        manifest = build_manifest(
            source_id="yahoo",
            endpoint=endpoint,
            params=params,
            raw_bytes=transformed,
            http_status=response.status_code,
            parser_version=1,
        )
        return RawFetch(manifest=manifest, body=transformed)
