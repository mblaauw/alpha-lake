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
from alpha_lake.serving import read_bars_adjusted, read_bars_asof
from alpha_lake.transport._shared import (
    _INDICATOR_MAP,
    _MAX_LOOKBACK_DAYS,
    _compute_warmup,
    _now,
    _parse_indicators,
    _pl_to_dicts,
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


@app.get("/v1/health")
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

    # resolve() expects a date (effective_start/effective_end are DATE columns)
    sec_id = resolve_security(_get_con(), symbol, as_of=as_of.date())
    if sec_id is None:
        raise HTTPException(404, f"Symbol '{symbol}' not found")

    kwargs: dict[str, Any] = {"security_ids": [sec_id], "as_of": as_of}
    if start:
        kwargs["start_date"] = start
    if end:
        kwargs["end_date"] = end
    if snapshot_id:
        kwargs["snapshot_id"] = snapshot_id
    if price_mode != "raw":
        kwargs["price_mode"] = price_mode

    if price_mode != "raw":
        df = read_bars_adjusted(_get_con(), **kwargs)
    else:
        df = read_bars_asof(_get_con(), **kwargs)
    return JSONResponse(_pl_to_dicts(df))


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

    # resolve() expects a date (effective_start/effective_end are DATE columns)
    sec_id = resolve_security(_get_con(), symbol, as_of=as_of.date())
    if sec_id is None:
        raise HTTPException(404, f"Symbol '{symbol}' not found")

    parsed = _parse_indicators(indicators)
    for name, _args in parsed:
        if name not in _INDICATOR_MAP:
            raise HTTPException(422, f"Unknown indicator: {name}")

    warmup_start = start
    for name, args in parsed:
        w = _compute_warmup(name, args, start)
        if w and (warmup_start is None or w < warmup_start):
            warmup_start = w

    kwargs: dict[str, Any] = {"security_ids": [sec_id], "as_of": as_of}
    if warmup_start:
        kwargs["start_date"] = warmup_start
    if end:
        kwargs["end_date"] = end

    bars_df = read_bars_asof(_get_con(), **kwargs)
    if bars_df.height == 0:
        return JSONResponse([])

    bars_df = bars_df.sort("effective_date")
    result = bars_df.to_dict(as_series=False)
    result["effective_date"] = [str(d) for d in result["effective_date"]]

    for name, args in parsed:
        fn = _INDICATOR_MAP[name]
        if name == "atr":
            series = fn(bars_df["high"], bars_df["low"], bars_df["close"], *args)
            result[name] = [float(x) if x is not None else None for x in series]
        elif name in ("bollinger", "macd"):
            bands = fn(bars_df["close"], *args)
            if isinstance(bands, dict):
                for k, v in bands.items():
                    result[f"{name}_{k}"] = [float(x) if x is not None else None for x in v]
        else:
            series = fn(bars_df["close"], *args)
            result[name] = [float(x) if x is not None else None for x in series]

    if start and warmup_start and warmup_start < start:
        mask = [str(d) >= start.isoformat() for d in result["effective_date"]]
        for key in list(result.keys()):
            result[key] = [v for v, m in zip(result[key], mask, strict=True) if m]

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


@app.get("/service-worker.js")
async def service_worker():
    sw = _STATIC / "service-worker.js"
    if not sw.exists():
        raise HTTPException(404)
    return FileResponse(sw, media_type="application/javascript")


@app.get("/manifest.webmanifest")
async def manifest():
    mf = _STATIC / "manifest.webmanifest"
    if not mf.exists():
        raise HTTPException(404)
    return FileResponse(mf, media_type="application/manifest+json")


# ── Dashboard API router —───────────────────────────────────────────────────

from alpha_lake.transport.dashboard import router as dashboard_router  # noqa: E402

app.include_router(dashboard_router)
