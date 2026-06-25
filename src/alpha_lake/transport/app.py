"""FastAPI application for the Alpha-Lake REST API.

This module defines the authenticated REST endpoints (/v1/bars, /v1/health, …),
the dashboard gate, and static file mounting. Shared indicator/format utilities
live in ``_shared.py``.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import date, datetime
from pathlib import Path
from time import monotonic

import duckdb
from fastapi import FastAPI, HTTPException, Request  # type: ignore[unresolved-import]
from fastapi.responses import FileResponse, JSONResponse  # type: ignore[unresolved-import]
from fastapi.staticfiles import StaticFiles  # type: ignore[unresolved-import]

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
    _fetch_bars,
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
    )

    if df.is_empty():
        raise HTTPException(404, f"No data for symbol: {symbol}")

    rows = df.rows(named=True)
    metrics = [_fundamental_row_to_item(r, include_set) for r in rows]

    return JSONResponse(
        {
            "symbol": symbol,
            "as_of": as_of.isoformat(),
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


# ── Dashboard / static —─────────────────────────────────────────────────────

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


# ── Dashboard API router —───────────────────────────────────────────────────

from alpha_lake.transport.dashboard import router as dashboard_router  # noqa: E402

app.include_router(dashboard_router)
