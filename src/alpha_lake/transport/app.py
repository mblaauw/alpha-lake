"""FastAPI application for the Alpha-Lake REST API.

This module defines the authenticated REST endpoints (/v1/bars, /v1/health, ),
the dashboard gate, and static file mounting. Shared indicator/format utilities
live in ``_shared.py``.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import date, datetime, timedelta
from pathlib import Path
from time import monotonic

import duckdb
from fastapi import FastAPI, HTTPException, Request  # type: ignore[unresolved-import]
from fastapi.responses import FileResponse, JSONResponse  # type: ignore[unresolved-import]
from fastapi.staticfiles import StaticFiles  # type: ignore[unresolved-import]

from alpha_lake.calendar_ import is_trading_day
from alpha_lake.catalog import catalog_health, connect
from alpha_lake.config import get_config, load_config
from alpha_lake.interpretation.fundamentals_glossary import glossary_to_json
from alpha_lake.secrets import get_store
from alpha_lake.security_master import resolve as resolve_security
from alpha_lake.serving import read_fundamental_metrics_asof
from alpha_lake.transport._models import (
    HealthResponse,
)
from alpha_lake.transport._shared import (
    _INDICATOR_MAP,
    _MAX_LOOKBACK_DAYS,
    _compute_and_serialize_indicators,
    _dataset_health,
    _fetch_bars,
    _fetch_dataset,
    _fundamental_row_to_item,
    _now,
    _parse_indicators,
    _validate_price_mode,
)

_STATIC = Path(__file__).parent / "static"


class _TokenBucket:
    def __init__(self, rate: float, burst: int) -> None:
        self.rate = rate
        self.burst = burst
        self._tokens = float(burst)
        self._last = monotonic()

    def consume(self) -> bool:
        now = monotonic()
        elapsed = now - self._last
        self._tokens = min(float(self.burst), self._tokens + elapsed * self.rate)
        self._last = now
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False


def _verify_key(key: str) -> bool:
    store = get_store()
    suffix = (
        "live" if key.startswith("al_live_") else "test" if key.startswith("al_test_") else None
    )
    if suffix is None:
        return False
    stored = store.get(f"alpha_lake_api_key_{suffix}")
    if not stored:
        return False
    return hmac.compare_digest(
        hashlib.sha256(key.encode()).hexdigest(),
        hashlib.sha256(stored.encode()).hexdigest(),
    )


_connection: duckdb.DuckDBPyConnection | None = None
_buckets: dict[str, _TokenBucket] = {}


def _get_con() -> duckdb.DuckDBPyConnection:
    global _connection
    if _connection is None:
        _connection = connect(load_config())
    return _connection


def _auth(request: Request) -> str:
    key = request.headers.get("X-API-Key") or request.headers.get("Authorization", "").removeprefix(
        "Bearer "
    )
    if not key:
        raise HTTPException(401, "Missing API key")
    if not _verify_key(key):
        raise HTTPException(401, "Invalid API key")
    bucket = _buckets.get(key)
    if bucket is None:
        bucket = _buckets[key] = _TokenBucket(rate=10.0, burst=20)
    if not bucket.consume():
        raise HTTPException(429, "Rate limit exceeded — single-replica limit")
    return key


app = FastAPI(title="Alpha-Lake", version="0.1.0")


@app.get("/v1/health", response_model=HealthResponse)
async def health():
    try:
        return catalog_health(_get_con())
    except Exception as exc:
        return {"snapshots": 0, "latest_snapshot_id": None, "status": "error", "detail": str(exc)}


@app.get("/v1/bars")
async def bars(
    request: Request,
    symbol: str,
    start: date | None = None,
    end: date | None = None,
    as_of: datetime | None = None,
    snapshot_id: str | None = None,
    price_mode: str = "raw",
):
    _auth(request)

    if as_of is None:
        as_of = _now()

    if start and end and (end - start).days > _MAX_LOOKBACK_DAYS:
        raise HTTPException(422, f"Lookback exceeds max of {_MAX_LOOKBACK_DAYS} days")

    _validate_price_mode(price_mode)
    con = _get_con()
    sec_id = resolve_security(con, symbol, as_of=as_of.date())
    result = _fetch_bars(
        con, sec_id, as_of, start=start, end=end, snapshot_id=snapshot_id, price_mode=price_mode
    )
    if not result:
        raise HTTPException(404, f"Unknown symbol or no bars available: {symbol}")
    return JSONResponse(result)


@app.get("/v1/bars/indicators")
async def bars_indicators(
    request: Request,
    symbol: str,
    indicators: str,
    start: date | None = None,
    end: date | None = None,
    as_of: datetime | None = None,
):
    _auth(request)

    if as_of is None:
        as_of = _now()

    if start and end and (end - start).days > _MAX_LOOKBACK_DAYS:
        raise HTTPException(422, f"Lookback exceeds max of {_MAX_LOOKBACK_DAYS} days")

    con = _get_con()
    sec_id = resolve_security(con, symbol, as_of=as_of.date())

    parsed = _parse_indicators(indicators)
    for name, _args in parsed:
        if name not in _INDICATOR_MAP:
            raise HTTPException(422, f"Unknown indicator: {name}")

    result = _compute_and_serialize_indicators(con, sec_id, parsed, as_of, start=start, end=end)
    if not result:
        raise HTTPException(404, f"Unknown symbol or no bars available: {symbol}")
    return JSONResponse(result)


# ── Fundamentals ──────────────────────────────────────────────────────────────


@app.get("/v1/fundamentals/metrics")
async def fundamentals_metrics(
    request: Request,
    symbol: str,
    as_of: datetime | None = None,
    snapshot_id: str | None = None,
    categories: str | None = None,
    metric_ids: str | None = None,
    include: str | None = None,
    price_mode: str = "raw",
):
    _auth(request)

    if as_of is None:
        raise HTTPException(422, "as_of is required for fundamental metric research reads")

    _validate_price_mode(price_mode)
    con = _get_con()
    sec_id = resolve_security(con, symbol, as_of=as_of.date())

    cat_list = [c.strip() for c in categories.split(",") if c.strip()] if categories else None
    mid_list = [m.strip() for m in metric_ids.split(",") if m.strip()] if metric_ids else None
    include_set = {s.strip() for s in include.split(",") if s.strip()} if include else set()

    df = read_fundamental_metrics_asof(
        con,
        security_ids=[sec_id],
        as_of=as_of,
        categories=cat_list,
        metric_ids=mid_list,
        price_mode=price_mode,
        snapshot_id=snapshot_id,
    )

    if df.is_empty():
        raise HTTPException(404, f"No data for symbol: {symbol}")

    rows = df.rows(named=True)
    metrics = [_fundamental_row_to_item(r, include_set) for r in rows]

    return JSONResponse(
        {
            "symbol": symbol,
            "as_of": as_of.isoformat(),
            "snapshot_id": snapshot_id,
            "metrics": metrics,
            "metadata": {
                "computed_at": _now().isoformat(),
                "metrics_returned": len(metrics),
            },
        }
    )


@app.get("/v1/fundamentals/glossary")
async def fundamentals_glossary(
    request: Request,
    categories: str | None = None,
):
    _auth(request)
    payloads = glossary_to_json()
    if categories:
        wanted = {c.strip() for c in categories.split(",") if c.strip()}
        payloads = [p for p in payloads if p["category"] in wanted]
    return JSONResponse(payloads)


# ── Contract ────────────────────────────────────────────────────────────────


@app.get("/v1/contract")
async def contract():
    return {
        "service": "alpha-lake",
        "api_version": "1.0",
        "minimum_alpha_quant_version": "0.3.0",
        "capabilities": [
            "pit_bars",
            "technical_indicators",
            "fundamental_metrics",
            "insider_facts",
            "earnings_events",
            "attention_metrics",
            "snapshot_reads",
        ],
    }


# ── Universe ────────────────────────────────────────────────────────────────


@app.get("/v1/universe")
async def universe(
    request: Request,
    as_of: date | None = None,
):
    _auth(request)
    con = _get_con()
    if as_of:
        rows = con.execute(
            "SELECT DISTINCT symbol, security_id, name FROM security_master"
            " WHERE (effective_start IS NULL OR effective_start <= ?)"
            " AND (effective_end IS NULL OR effective_end >= ?)"
            " ORDER BY symbol",
            [as_of, as_of],
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT DISTINCT symbol, security_id, name FROM security_master ORDER BY symbol"
        ).fetchall()
    members = [{"symbol": r[0], "security_id": r[1], "name": r[2] or ""} for r in rows]
    return JSONResponse({"as_of": as_of.isoformat() if as_of else None, "members": members})


# ── Decision Panel — batch PIT snapshot ──────────────────────────────────────


from alpha_lake.serving import read_fundamental_metrics_asof


@app.get("/v1/decision-panel")
async def decision_panel(
    request: Request,
    symbols: str,
    as_of: datetime,
    snapshot_id: str | None = None,
    indicators: str = "sma:20,50,200,ema:12,26,rsi:14,atr:14,macd:12,26,9,bollinger:20",
    metric_categories: str = "valuation,profitability,growth,financial_health,efficiency,liquidity",
):
    _auth(request)
    con = _get_con()
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        raise HTTPException(422, "At least one symbol is required")

    results: dict[str, object] = {}
    for symbol in symbol_list:
        sec_id = resolve_security(con, symbol, as_of=as_of.date())
        if sec_id is None:
            continue

        bars = _fetch_bars(
            con,
            sec_id,
            as_of,
            end=as_of.date(),
            snapshot_id=snapshot_id,
            price_mode="split_adjusted",
        )

        parsed_indicators = _parse_indicators(indicators)
        tech = (
            _compute_and_serialize_indicators(
                con,
                sec_id,
                parsed_indicators,
                as_of,
                end=as_of.date(),
            )
            if bars
            else {}
        )

        cat_list = [c.strip() for c in metric_categories.split(",") if c.strip()]
        fund_df = read_fundamental_metrics_asof(
            con,
            security_ids=[sec_id],
            as_of=as_of,
            categories=cat_list,
            price_mode="split_adjusted",
            snapshot_id=snapshot_id,
        )
        fund_metrics = (
            [_fundamental_row_to_item(r, set()) for r in fund_df.rows(named=True)]
            if not fund_df.is_empty()
            else []
        )

        insider_rows = _fetch_dataset(
            con,
            "insider_tx",
            sec_id,
            as_of,
            snapshot_id=snapshot_id,
            source_precedence_dataset="insider_tx",
        )
        earnings_rows = _fetch_dataset(
            con,
            "earnings_calendar",
            sec_id,
            as_of,
            start=as_of.date() - __import__("datetime").timedelta(days=90),
            end=as_of.date(),
            snapshot_id=snapshot_id,
        )
        mention_rows = _fetch_dataset(
            con,
            "attention_metrics",
            sec_id,
            as_of,
            start=as_of.date() - __import__("datetime").timedelta(days=30),
            end=as_of.date(),
            snapshot_id=snapshot_id,
        )

        results[symbol] = {
            "bars": bars,
            "indicators": tech,
            "fundamentals": fund_metrics,
            "insider_transactions": insider_rows,
            "earnings_events": earnings_rows,
            "attention_mentions": mention_rows,
        }

    return JSONResponse(
        {
            "as_of": as_of.isoformat(),
            "snapshot_id": snapshot_id,
            "symbols": symbol_list,
            "panels": results,
        }
    )


# ── Insider Transactions ────────────────────────────────────────────────────


@app.get("/v1/insider-transactions/{symbol}")
async def insider_transactions(
    request: Request,
    symbol: str,
    as_of: datetime | None = None,
    snapshot_id: str | None = None,
):
    _auth(request)
    if as_of is None:
        as_of = _now()
    con = _get_con()
    sec_id = resolve_security(con, symbol, as_of=as_of.date())
    rows = _fetch_dataset(
        con,
        "insider_tx",
        sec_id,
        as_of,
        snapshot_id=snapshot_id,
        source_precedence_dataset="insider_tx",
    )
    if not rows:
        raise HTTPException(404, f"No insider data for symbol: {symbol}")
    return JSONResponse({"symbol": symbol, "as_of": as_of.isoformat(), "transactions": rows})


# ── Earnings Calendar ───────────────────────────────────────────────────────


@app.get("/v1/earnings-calendar")
async def earnings_calendar(
    request: Request,
    symbol: str | None = None,
    start: date | None = None,
    end: date | None = None,
    as_of: datetime | None = None,
    snapshot_id: str | None = None,
):
    _auth(request)
    if as_of is None:
        as_of = _now()
    con = _get_con()
    sec_id = resolve_security(con, symbol, as_of=as_of.date()) if symbol else None
    if sec_id is None and symbol:
        raise HTTPException(404, f"Unknown symbol: {symbol}")
    rows = _fetch_dataset(
        con,
        "earnings_calendar",
        sec_id or "",
        as_of,
        start=start,
        end=end,
        snapshot_id=snapshot_id,
    )
    return JSONResponse({"as_of": as_of.isoformat(), "earnings": rows})


# ── Attention Metrics ───────────────────────────────────────────────────────


@app.get("/v1/attention-metrics/{symbol}")
async def attention_metrics(
    request: Request,
    symbol: str,
    days: int = 30,
    as_of: datetime | None = None,
    snapshot_id: str | None = None,
):
    _auth(request)
    if as_of is None:
        as_of = _now()
    con = _get_con()
    sec_id = resolve_security(con, symbol, as_of=as_of.date())
    start = as_of.date() - timedelta(days=days - 1)
    rows = _fetch_dataset(
        con,
        "attention_metrics",
        sec_id,
        as_of,
        start=start,
        end=as_of.date(),
        snapshot_id=snapshot_id,
    )
    if not rows:
        raise HTTPException(404, f"No attention data for symbol: {symbol}")
    return JSONResponse({"symbol": symbol, "as_of": as_of.isoformat(), "mentions": rows})


# ── Trading Calendar ────────────────────────────────────────────────────────


@app.get("/v1/trading-calendar")
async def trading_calendar(
    request: Request,
    start: date,
    end: date,
    as_of: datetime | None = None,
):
    _auth(request)
    _ = as_of
    days: list[dict[str, object]] = []
    current = start
    while current <= end:
        open_day = is_trading_day(current)
        days.append(
            {
                "date": current.isoformat(),
                "is_open": open_day,
                "session": "regular" if open_day else None,
            }
        )
        current += timedelta(days=1)
    return JSONResponse({"start": start.isoformat(), "end": end.isoformat(), "days": days})


# ── Dataset Health ──────────────────────────────────────────────────────────


@app.get("/v1/dataset-health")
async def dataset_health(
    request: Request,
    snapshot_id: str | None = None,
):
    _auth(request)
    con = _get_con()
    tables = [
        "lake_bars",
        "fundamentals",
        "insider_tx",
        "earnings_calendar",
        "attention_metrics",
    ]
    return _dataset_health(con, tables, snapshot_id=snapshot_id)


# ── Dashboard / static ──────────────────────────────────────────────────────

_DASHBOARD_ENABLED: bool | None = None


def _dashboard_enabled() -> bool:
    global _DASHBOARD_ENABLED
    if _DASHBOARD_ENABLED is None:
        try:
            load_config()
            _DASHBOARD_ENABLED = get_config().transport.dashboard_enabled
        except Exception:
            _DASHBOARD_ENABLED = False
    return _DASHBOARD_ENABLED


if _STATIC.is_dir():
    app.mount("/static", StaticFiles(directory=_STATIC), name="static")


@app.get("/")
async def home():
    if not _dashboard_enabled():
        raise HTTPException(404)
    if not (_STATIC / "index.html").exists():
        raise HTTPException(404)
    return FileResponse(_STATIC / "index.html")


@app.get("/manifest.webmanifest")
async def manifest():
    mf = _STATIC / "manifest.webmanifest"
    if not mf.exists():
        raise HTTPException(404)
    return FileResponse(mf, media_type="application/manifest+json")


@app.get("/service-worker.js")
async def service_worker():
    sw = _STATIC / "service-worker.js"
    if not sw.exists():
        raise HTTPException(404)
    return FileResponse(sw, media_type="application/javascript")


# ── Dashboard API router ────────────────────────────────────────────────────

from alpha_lake.transport.dashboard import router as dashboard_router  # noqa: E402

app.include_router(dashboard_router)
