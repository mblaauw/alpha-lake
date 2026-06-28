from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from alpha_lake.connectors.base import RawFetch, build_manifest, check_budget
from alpha_lake.source_registry import get_source

_AV_BASE = "https://www.alphavantage.co"


async def _alphav_fetch(params: dict[str, Any]) -> RawFetch:
    """Execute a single AV API call and return the RawFetch."""
    cfg = get_source("alphav")
    check_budget(cfg)
    params["apikey"] = cfg.api_key
    async with httpx.AsyncClient(base_url=_AV_BASE, timeout=30.0) as c:
        r = await c.get("/query", params=params)
        r.raise_for_status()
    manifest = build_manifest("alphav", "/query", params, r.content, r.status_code, 1)
    return RawFetch(manifest=manifest, body=r.content)


async def fetch_fundamentals(symbol: str) -> RawFetch:
    """Fetch INCOME_STATEMENT, BALANCE_SHEET, CASH_FLOW, OVERVIEW, SHARES_OUTSTANDING,
    EARNINGS, EARNINGS_ESTIMATES sequentially with 12-second rate-limit gaps."""

    async def _fetch_one(function: str) -> dict[str, Any]:
        rf = await _alphav_fetch({"function": function, "symbol": symbol})
        return json.loads(rf.body)

    sections = [
        "INCOME_STATEMENT",
        "BALANCE_SHEET",
        "CASH_FLOW",
        "OVERVIEW",
        "SHARES_OUTSTANDING",
        "EARNINGS",
        "EARNINGS_ESTIMATES",
    ]
    results: dict[str, dict[str, Any]] = {}
    for i, fn in enumerate(sections):
        results[fn.lower().replace("-", "_")] = await _fetch_one(fn)
        if i < len(sections) - 1:
            await asyncio.sleep(12)

    merged = {"source": "alphav", "symbol": symbol, **results}
    body = json.dumps(merged, default=str).encode()
    return RawFetch(manifest=build_manifest("alphav", "/query", {}, body, 200, 1), body=body)


async def fetch_insider_transactions(symbol: str) -> RawFetch:
    return await _alphav_fetch({"function": "INSIDER_TRANSACTIONS", "symbol": symbol})


async def fetch_institutional_holdings(symbol: str) -> RawFetch:
    return await _alphav_fetch({"function": "INSTITUTIONAL_HOLDINGS", "symbol": symbol})


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
    """Fetch an economic indicator from AV. ``from_date``/``to_date`` unused (free tier)."""
    del from_date, to_date
    spec = _ECON_SERIES_MAP.get(series_id)
    if spec is None:
        raise ValueError(f"Unknown economic series: {series_id}")
    params = {k: v for k, v in spec.items() if v}
    return await _alphav_fetch(params)


async def fetch_corp_actions(symbol: str) -> RawFetch:
    """Fetch DIVIDENDS and SPLITS. Merges both into one RawFetch."""
    div_rf = await _alphav_fetch({"function": "DIVIDENDS", "symbol": symbol})
    await asyncio.sleep(12)
    spl_rf = await _alphav_fetch({"function": "SPLITS", "symbol": symbol})
    merged = {
        "source": "alphav",
        "symbol": symbol,
        "dividends": json.loads(div_rf.body),
        "splits": json.loads(spl_rf.body),
    }
    return RawFetch(
        manifest=build_manifest(
            "alphav", "/query", {}, json.dumps(merged, default=str).encode(), 200, 1
        ),
        body=json.dumps(merged, default=str).encode(),
    )


async def fetch_top_movers() -> RawFetch:
    return await _alphav_fetch({"function": "TOP_GAINERS_LOSERS"})


async def fetch_etf_profile(symbol: str) -> RawFetch:
    return await _alphav_fetch({"function": "ETF_PROFILE", "symbol": symbol})


async def fetch_ipo_calendar() -> RawFetch:
    return await _alphav_fetch({"function": "IPO_CALENDAR"})
