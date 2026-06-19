from __future__ import annotations

from typing import Any

import httpx

from alpha_lake.connectors.base import RawFetch, build_manifest
from alpha_lake.source_registry import get_source


def _build_client(cfg) -> httpx.AsyncClient:
    headers = {"Content-Type": "application/json"}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"
    return httpx.AsyncClient(base_url=cfg.base_url, headers=headers, timeout=30.0)


async def map_to_figi(
    id_type: str,
    id_value: str,
    exchange_code: str | None = None,
    security_type: str | None = None,
) -> RawFetch:
    """Map a ticker/ISIN to FIGI using the OpenFIGI API.

    Args:
        id_type: 'TICKER', 'ID_ISIN', 'ID_BB_UNIQUE', etc.
        id_value: The identifier value.
        exchange_code: Optional exchange filter (e.g. 'US').
        security_type: Optional security type filter (e.g. 'Common Stock').
    """
    cfg = get_source("openfigi")
    body: list[dict[str, Any]] = [{"idType": id_type, "idValue": id_value}]
    if exchange_code:
        body[0]["exchangeCode"] = exchange_code
    if security_type:
        body[0]["securityType"] = security_type

    async with _build_client(cfg) as client:
        response = await client.post("/mapping", json=body)
        raw_bytes = response.content
        manifest = build_manifest(
            source_id="openfigi",
            endpoint="/mapping",
            params={"idType": id_type, "idValue": id_value},
            raw_bytes=raw_bytes,
            http_status=response.status_code,
            parser_version=1,
        )
        return RawFetch(manifest=manifest, body=raw_bytes)
