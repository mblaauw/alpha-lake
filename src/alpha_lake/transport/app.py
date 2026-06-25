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
from typing import Any

import duckdb
from fastapi import FastAPI, HTTPException, Request  # type: ignore[unresolved-import]
from fastapi.responses import FileResponse, JSONResponse  # type: ignore[unresolved-import]
from fastapi.staticfiles import StaticFiles  # type: ignore[unresolved-import]

from alpha_lake.catalog import catalog_health, connect
from alpha_lake.config import get_config, load_config
from alpha_lake.secrets import get_store
from alpha_lake.security_master import resolve as resolve_security
from alpha_lake.transport._models import HealthResponse
from alpha_lake.transport._shared import (
    _INDICATOR_MAP,
    _MAX_LOOKBACK_DAYS,
    _compute_and_serialize_indicators,
    _fetch_bars,
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
    return catalog_health(_get_con())


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
    return JSONResponse(
        _fetch_bars(
            con, sec_id, as_of, start=start, end=end, snapshot_id=snapshot_id, price_mode=price_mode
        )
    )


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
    return JSONResponse(result)


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


# ── Dashboard API router —───────────────────────────────────────────────────

from alpha_lake.transport.dashboard import router as dashboard_router  # noqa: E402

app.include_router(dashboard_router)
