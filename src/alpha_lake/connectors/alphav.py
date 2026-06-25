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


_ECON_SERIES_MAP: dict[str, dict[str, Any]] = {
    "gdp": {"function": "REAL_GDP"},
    "gdp_per_capita": {"function": "REAL_GDP_PER_CAPITA"},
    "treasury_3mo": {"function": "TREASURY_YIELD", "interval": "daily", "maturity": "3month"},
    "treasury_2yr": {"function": "TREASURY_YIELD", "interval": "daily", "maturity": "2year"},
    "treasury_5yr": {"function": "TREASURY_YIELD", "interval": "daily", "maturity": "5year"},
    "treasury_7yr": {"function": "TREASURY_YIELD", "interval": "daily", "maturity": "7year"},
    "treasury_10yr": {"function": "TREASURY_YIELD", "interval": "daily", "maturity": "10year"},
    "treasury_30yr": {"function": "TREASURY_YIELD", "interval": "daily", "maturity": "30year"},
    "fed_rate": {"function": "FEDERAL_FUNDS_RATE"},
    "cpi": {"function": "CPI"},
    "inflation": {"function": "INFLATION"},
    "retail_sales": {"function": "RETAIL_SALES"},
    "durables": {"function": "DURABLES"},
    "unemployment": {"function": "UNEMPLOYMENT"},
    "nonfarm_payroll": {"function": "NONFARM_PAYROLL"},
    # Commodities
    "wti": {"function": "WTI"},
    "brent": {"function": "BRENT"},
    "natural_gas": {"function": "NATURAL_GAS"},
    "copper": {"function": "COPPER"},
    "aluminum": {"function": "ALUMINUM"},
    "wheat": {"function": "WHEAT"},
    "corn": {"function": "CORN"},
    "cotton": {"function": "COTTON"},
    "sugar": {"function": "SUGAR"},
    "coffee": {"function": "COFFEE"},
    "all_commodities": {"function": "ALL_COMMODITIES"},
}


async def fetch_econ_indicator(series_id: str, from_date: str = "", to_date: str = "") -> RawFetch:
    """Fetch an economic indicator from Alpha Vantage.

    Maps ``series_id`` to the appropriate AV function. Single API call.
    ``from_date`` and ``to_date`` are accepted for pipeline compatibility
    but AV free tier returns all available data regardless.
    """
    del from_date, to_date  # unused — AV free tier always returns full history
    cfg = get_source("alphav")
    check_budget(cfg)
    spec = _ECON_SERIES_MAP.get(series_id)
    if spec is None:
        raise ValueError(f"Unknown economic series: {series_id}")
    params: dict[str, Any] = {"apikey": cfg.api_key, **spec}
    # Remove default empty strings that AV may reject
    params = {k: v for k, v in params.items() if v}
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


async def fetch_top_movers() -> RawFetch:
    """Fetch TOP_GAINERS_LOSERS. Single call, no symbol needed."""
    cfg = get_source("alphav")
    check_budget(cfg)
    params = {"apikey": cfg.api_key, "function": "TOP_GAINERS_LOSERS"}
    async with httpx.AsyncClient(base_url=_AV_BASE, timeout=30.0) as c:
        r = await c.get("/query", params=params)
        r.raise_for_status()
        body = r.content
    manifest = build_manifest("alphav", "/query", params, body, r.status_code, 1)
    return RawFetch(manifest=manifest, body=body)


async def fetch_etf_profile(symbol: str) -> RawFetch:
    """Fetch ETF_PROFILE for a symbol."""
    cfg = get_source("alphav")
    check_budget(cfg)
    params = {"apikey": cfg.api_key, "symbol": symbol, "function": "ETF_PROFILE"}
    async with httpx.AsyncClient(base_url=_AV_BASE, timeout=30.0) as c:
        r = await c.get("/query", params=params)
        r.raise_for_status()
        body = r.content
    manifest = build_manifest("alphav", "/query", params, body, r.status_code, 1)
    return RawFetch(manifest=manifest, body=body)


async def fetch_ipo_calendar() -> RawFetch:
    """Fetch IPO_CALENDAR. Single call, no symbol needed."""
    cfg = get_source("alphav")
    check_budget(cfg)
    params = {"apikey": cfg.api_key, "function": "IPO_CALENDAR"}
    async with httpx.AsyncClient(base_url=_AV_BASE, timeout=30.0) as c:
        r = await c.get("/query", params=params)
        r.raise_for_status()
        body = r.content
    manifest = build_manifest("alphav", "/query", params, body, r.status_code, 1)
    return RawFetch(manifest=manifest, body=body)


async def fetch_listing_status() -> RawFetch:
    """Fetch LISTING_STATUS. Returns active/delisted US stocks & ETFs."""
    cfg = get_source("alphav")
    check_budget(cfg)
    params = {"apikey": cfg.api_key, "function": "LISTING_STATUS"}
    async with httpx.AsyncClient(base_url=_AV_BASE, timeout=30.0) as c:
        r = await c.get("/query", params=params)
        r.raise_for_status()
        body = r.content
    manifest = build_manifest("alphav", "/query", params, body, r.status_code, 1)
    return RawFetch(manifest=manifest, body=body)
