from __future__ import annotations

import csv
import io
import json
from datetime import date
from typing import Any

from alpha_lake.connectors.base import (
    RawFetch,
    build_client,
    build_manifest,
    check_budget,
    fetch_with_retry,
)
from alpha_lake.source_registry import get_source


async def fetch_macro_series(
    series_id: str,
    from_date: str = "",
    to_date: str = "",
) -> RawFetch:
    """Fetch a FRED macroeconomic series as a raw JSON observation list.

    Uses the keyed endpoint at ``api.stlouisfed.org/fred/series/observations``
    with ``api_key`` as a query parameter (not Bearer auth). Falls back to the
    keyless ``fredgraph.csv`` endpoint when the key is empty (Phase 0.2).

    FRED's ``realtime_start``/``realtime_end`` are set to today when not
    provided, so the response reflects the *latest known* vintage. Callers
    should pass explicit realtime bounds to retrieve historical vintages.
    """
    cfg = get_source("fred")
    check_budget(cfg)

    today = date.today().isoformat()
    params: dict[str, Any] = {
        "series_id": series_id,
        "file_type": "json",
        "realtime_start": from_date or today,
        "realtime_end": to_date or today,
    }

    if cfg.api_key:
        params["api_key"] = cfg.api_key
        endpoint = "/fred/series/observations"
    else:
        endpoint = "/fredgraph.csv"
        params.pop("file_type", None)
        params.pop("realtime_start", None)
        params.pop("realtime_end", None)
        params["id"] = params.pop("series_id")

    async with build_client(cfg) as client:
        response = await fetch_with_retry(client, endpoint, params=params)
        body = response.content
        if not cfg.api_key:
            raw = body.decode()
            reader = csv.DictReader(io.StringIO(raw))
            observations = [
                {"date": row["observation_date"], "value": row.get(series_id, "")} for row in reader
            ]
            body = json.dumps({"observations": observations}).encode()
        manifest = build_manifest(
            "fred",
            endpoint,
            params,
            response.content,
            response.status_code,
            1,
            key_mode="keyed" if cfg.api_key else "keyless",
        )
        return RawFetch(manifest=manifest, body=body)
