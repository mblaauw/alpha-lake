from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from alpha_lake.connectors.base import RawFetch, build_manifest, check_budget
from alpha_lake.source_registry import get_source

_AV_BASE = "https://www.alphavantage.co"


async def fetch_fundamentals(symbol: str) -> RawFetch:
    """Fetch INCOME_STATEMENT, BALANCE_SHEET, CASH_FLOW, OVERVIEW, SHARES_OUTSTANDING.

    Free tier: 25 calls/day, 5 calls/min. Each symbol = 5 calls.
    Calls are sequenced with a 12-second gap to stay within rate limits.
    Returns merged JSON with all five sections in the ``body``.
    """
    cfg = get_source("alphav")
    check_budget(cfg)
    params: dict[str, Any] = {"apikey": cfg.api_key, "symbol": symbol}

    async def _fetch_one(function: str) -> dict[str, Any]:
        p = {**params, "function": function}
        async with httpx.AsyncClient(base_url=_AV_BASE, timeout=30.0) as c:
            r = await c.get("/query", params=p)
            r.raise_for_status()
            return r.json()

    is_data = await _fetch_one("INCOME_STATEMENT")
    await asyncio.sleep(12)
    bs_data = await _fetch_one("BALANCE_SHEET")
    await asyncio.sleep(12)
    cf_data = await _fetch_one("CASH_FLOW")
    await asyncio.sleep(12)
    ov_data = await _fetch_one("OVERVIEW")
    await asyncio.sleep(12)
    so_data = await _fetch_one("SHARES_OUTSTANDING")
    await asyncio.sleep(12)
    ea_data = await _fetch_one("EARNINGS")
    await asyncio.sleep(12)
    ee_data = await _fetch_one("EARNINGS_ESTIMATES")

    merged = {
        "source": "alphav",
        "symbol": symbol,
        "incomeStatement": is_data,
        "balanceSheet": bs_data,
        "cashFlow": cf_data,
        "overview": ov_data,
        "sharesOutstanding": so_data,
        "earnings": ea_data,
        "earningsEstimates": ee_data,
    }
    body = json.dumps(merged, default=str).encode()
    manifest = build_manifest(
        "alphav",
        "/query",
        params,
        body,
        200,
        1,
    )
    return RawFetch(manifest=manifest, body=body)


async def fetch_insider_transactions(symbol: str) -> RawFetch:
    """Fetch INSIDER_TRANSACTIONS for a symbol."""
    cfg = get_source("alphav")
    check_budget(cfg)
    params: dict[str, Any] = {
        "apikey": cfg.api_key,
        "symbol": symbol,
        "function": "INSIDER_TRANSACTIONS",
    }
    async with httpx.AsyncClient(base_url=_AV_BASE, timeout=30.0) as c:
        r = await c.get("/query", params=params)
        r.raise_for_status()
        body = r.content
    manifest = build_manifest("alphav", "/query", params, body, r.status_code, 1)
    return RawFetch(manifest=manifest, body=body)


async def fetch_institutional_holdings(symbol: str) -> RawFetch:
    """Fetch INSTITUTIONAL_HOLDINGS for a symbol."""
    cfg = get_source("alphav")
    check_budget(cfg)
    params = {"apikey": cfg.api_key, "symbol": symbol, "function": "INSTITUTIONAL_HOLDINGS"}
    async with httpx.AsyncClient(base_url=_AV_BASE, timeout=30.0) as c:
        r = await c.get("/query", params=params)
        r.raise_for_status()
        body = r.content
    manifest = build_manifest("alphav", "/query", params, body, r.status_code, 1)
    return RawFetch(manifest=manifest, body=body)


async def fetch_corp_actions(symbol: str) -> RawFetch:
    """Fetch DIVIDENDS and SPLITS for a symbol. Merges both into one RawFetch."""
    cfg = get_source("alphav")
    check_budget(cfg)
    params: dict[str, Any] = {"apikey": cfg.api_key, "symbol": symbol}

    async def _fetch_one(function: str) -> dict[str, Any]:
        p = {**params, "function": function}
        async with httpx.AsyncClient(base_url=_AV_BASE, timeout=30.0) as c:
            r = await c.get("/query", params=p)
            r.raise_for_status()
            return r.json()

    div_data = await _fetch_one("DIVIDENDS")
    await asyncio.sleep(12)
    spl_data = await _fetch_one("SPLITS")

    merged = {"source": "alphav", "symbol": symbol, "dividends": div_data, "splits": spl_data}
    body = json.dumps(merged, default=str).encode()
    manifest = build_manifest("alphav", "/query", params, body, 200, 1)
    return RawFetch(manifest=manifest, body=body)
