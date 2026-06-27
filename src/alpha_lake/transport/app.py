"""FastAPI application for the Alpha-Lake REST API.

This module defines the authenticated REST endpoints (/v1/bars, /v1/health, ),
the dashboard gate, and static file mounting. Shared indicator/format utilities
live in ``_shared.py``.
"""

from __future__ import annotations

import hashlib
import hmac
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from time import monotonic

import duckdb
from fastapi import FastAPI, HTTPException, Request  # type: ignore[unresolved-import]
from fastapi.responses import FileResponse, JSONResponse  # type: ignore[unresolved-import]
from fastapi.staticfiles import StaticFiles  # type: ignore[unresolved-import]

from alpha_lake.calendar_ import is_trading_day, previous_trading_day
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
    _aware,
    _compute_and_serialize_indicators,
    _dataset_health,
    _fetch_bars,
    _fetch_dataset,
    _fundamental_row_to_item,
    _now,
    _parse_fields,
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
    stored = store.get(f"api_key_{suffix}")
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


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """Startup: ensure STOOQ Parquet, registry, and backfill."""
    try:
        con = _get_con()
        from alpha_lake.flows.bootstrap import ensure_registry

        ensure_registry(con)
    except Exception as exc:
        import logging

        logging.warning("Bootstrap startup skipped: %s", exc)
    yield


app = FastAPI(title="Alpha-Lake", version="0.1.0", lifespan=_lifespan)


@app.get("/v1/health", response_model=HealthResponse)
async def health():
    try:
        return catalog_health(_get_con())
    except Exception as exc:
        return {"snapshots": 0, "latest_snapshot_id": None, "status": "error", "detail": str(exc)}


def _parse_include(include: str | None) -> set[str]:
    return {s.strip() for s in include.split(",") if s.strip()} if include else set()


@app.get("/v1/bars")
async def bars(
    request: Request,
    symbol: str,
    start: date | None = None,
    end: date | None = None,
    as_of: datetime | None = None,
    snapshot_id: str | None = None,
    price_mode: str = "raw",
    include: str | None = None,
    fields: str | None = None,
):
    _auth(request)

    if as_of is None:
        as_of = _now()

    if start and end and (end - start).days > _MAX_LOOKBACK_DAYS:
        raise HTTPException(422, f"Lookback exceeds max of {_MAX_LOOKBACK_DAYS} days")

    _validate_price_mode(price_mode)
    con = _get_con()
    sec_id = resolve_security(con, symbol, as_of=as_of.date())
    if sec_id is None:
        raise HTTPException(404, f"Unknown symbol: {symbol}")
    result = _fetch_bars(
        con,
        sec_id,
        as_of,
        start=start,
        end=end,
        snapshot_id=snapshot_id,
        price_mode=price_mode,
        include_set=_parse_include(include),
        fields=_parse_fields(fields),
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
    include: str | None = None,
    fields: str | None = None,
):
    _auth(request)

    if as_of is None:
        as_of = _now()

    if start and end and (end - start).days > _MAX_LOOKBACK_DAYS:
        raise HTTPException(422, f"Lookback exceeds max of {_MAX_LOOKBACK_DAYS} days")

    con = _get_con()
    sec_id = resolve_security(con, symbol, as_of=as_of.date())
    if sec_id is None:
        raise HTTPException(404, f"Unknown symbol: {symbol}")

    parsed = _parse_indicators(indicators)
    for name, _args in parsed:
        if name not in _INDICATOR_MAP:
            raise HTTPException(422, f"Unknown indicator: {name}")

    result = _compute_and_serialize_indicators(
        con,
        sec_id,
        parsed,
        as_of,
        start=start,
        end=end,
        include_set=_parse_include(include),
        fields=_parse_fields(fields),
    )
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
    if sec_id is None:
        raise HTTPException(404, f"Unknown symbol: {symbol}")

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


@app.get("/v1/decision-panel")
async def decision_panel(
    request: Request,
    symbols: str,
    as_of: datetime,
    snapshot_id: str | None = None,
    indicators: str = (
        "sma:20;sma:50;sma:200;ema:12;ema:26;rsi:14;atr:14;macd:12,26,9;bollinger:20,2"
    ),
    metric_categories: str = "valuation,profitability,growth,financial_health,efficiency,liquidity",
    include: str = "",
):
    _auth(request)
    con = _get_con()
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        raise HTTPException(422, "At least one symbol is required")

    include_set = {s.strip() for s in include.split(",") if s.strip()}
    results: dict[str, object] = {}
    for symbol in symbol_list:
        sec_id = resolve_security(con, symbol, as_of=as_of.date())
        if sec_id is None:
            continue

        panel: dict[str, object] = {}

        bars = _fetch_bars(
            con,
            sec_id,
            as_of,
            end=as_of.date(),
            snapshot_id=snapshot_id,
            price_mode="split_adjusted",
            include_set=include_set,
        )
        panel["bars"] = bars

        parsed_indicators = _parse_indicators(indicators)
        panel["indicators"] = (
            _compute_and_serialize_indicators(
                con,
                sec_id,
                parsed_indicators,
                as_of,
                end=as_of.date(),
                include_set=include_set,
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
        panel["fundamentals"] = (
            [_fundamental_row_to_item(r, include_set) for r in fund_df.rows(named=True)]
            if not fund_df.is_empty()
            else []
        )

        panel["insider_transactions"] = _fetch_dataset(
            con,
            "insider_tx",
            sec_id,
            as_of,
            snapshot_id=snapshot_id,
            source_precedence_dataset="insider_tx",
            include_set=include_set,
        )
        panel["earnings_events"] = _fetch_dataset(
            con,
            "earnings_calendar",
            sec_id,
            as_of,
            start=as_of.date() - timedelta(days=90),
            end=as_of.date(),
            snapshot_id=snapshot_id,
            include_set=include_set,
        )
        panel["attention_mentions"] = _fetch_dataset(
            con,
            "attention_metrics",
            sec_id,
            as_of,
            start=as_of.date() - timedelta(days=30),
            end=as_of.date(),
            snapshot_id=snapshot_id,
            include_set=include_set,
        )

        # Optional sections gated by include parameter
        if "readouts" in include_set:
            from alpha_lake.serving.readouts import compute_readouts

            panel["readouts"] = compute_readouts(
                con,
                symbol,
                as_of,
                snapshot_id=snapshot_id,
            )
        if "insider_transactions_detail" in include_set:
            panel["insider_transactions_detail"] = _fetch_dataset(
                con,
                "insider_transactions",
                sec_id,
                as_of,
                snapshot_id=snapshot_id,
                include_set=include_set,
            )

        results[symbol] = panel

    return JSONResponse(
        {
            "as_of": as_of.isoformat(),
            "snapshot_id": snapshot_id,
            "symbols": symbol_list,
            "capabilities": ["readouts", "insider_transactions_detail"],
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
    include: str | None = None,
    fields: str | None = None,
):
    _auth(request)
    if as_of is None:
        as_of = _now()
    con = _get_con()
    sec_id = resolve_security(con, symbol, as_of=as_of.date())
    if sec_id is None:
        raise HTTPException(404, f"Unknown symbol: {symbol}")
    rows = _fetch_dataset(
        con,
        "insider_tx",
        sec_id,
        as_of,
        snapshot_id=snapshot_id,
        source_precedence_dataset="insider_tx",
        include_set=_parse_include(include),
        fields=_parse_fields(fields),
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
    include: str | None = None,
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
        include_set=_parse_include(include),
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
    include: str | None = None,
):
    _auth(request)
    if as_of is None:
        as_of = _now()
    con = _get_con()
    sec_id = resolve_security(con, symbol, as_of=as_of.date())
    if sec_id is None:
        raise HTTPException(404, f"Unknown symbol: {symbol}")
    start = as_of.date() - timedelta(days=days - 1)
    rows = _fetch_dataset(
        con,
        "attention_metrics",
        sec_id,
        as_of,
        start=start,
        end=as_of.date(),
        snapshot_id=snapshot_id,
        include_set=_parse_include(include),
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


# ── Symbol Readouts (authenticated) ───────────────────────────────────────────


from pydantic import BaseModel  # noqa: E402


class BatchReadoutRequest(BaseModel):
    symbols: list[str]
    as_of: datetime | None = None
    latest: bool = False
    categories: str = ""
    readout_ids: str = ""
    snapshot_id: str | None = None


class FactsBundleRequest(BaseModel):
    symbols: list[str]
    as_of: datetime | None = None
    latest: bool = False
    categories: str = ""
    readout_ids: str = ""
    metric_ids: str = ""
    snapshot_id: str | None = None
    include: str = ""


@app.get("/v1/symbol/{symbol}/readouts")
async def authenticated_symbol_readouts(
    request: Request,
    symbol: str,
    as_of: datetime | None = None,
    latest: bool = False,
    categories: str = "",
    readout_ids: str = "",
    snapshot_id: str | None = None,
):
    _auth(request)
    if as_of is None and not latest:
        raise HTTPException(
            422, "as_of is required for research reads. Use latest=true for convenience."
        )
    as_of = (
        datetime.combine(previous_trading_day(_now().date()), datetime.min.time(), tzinfo=UTC)
        if as_of is None
        else _aware(as_of)
    )
    con = _get_con()
    from alpha_lake.serving.readouts import compute_readouts

    return JSONResponse(
        compute_readouts(
            con,
            symbol,
            as_of,
            snapshot_id=snapshot_id,
            categories=categories,
            readout_ids=readout_ids,
        )
    )


@app.post("/v1/readouts/batch")
async def batch_readouts(request: Request, body: BatchReadoutRequest):
    _auth(request)
    if not body.symbols:
        raise HTTPException(422, "At least one symbol is required")
    if body.as_of is None and not body.latest:
        raise HTTPException(
            422, "as_of is required for research reads. Use latest=true for convenience."
        )
    as_of = (
        datetime.combine(previous_trading_day(_now().date()), datetime.min.time(), tzinfo=UTC)
        if body.as_of is None
        else _aware(body.as_of)
    )
    con = _get_con()
    from alpha_lake.serving.readouts import compute_readouts

    items: dict[str, object] = {}
    errors: dict[str, str] = {}
    for sym in body.symbols:
        try:
            items[sym] = compute_readouts(
                con,
                sym,
                as_of,
                snapshot_id=body.snapshot_id,
                categories=body.categories,
                readout_ids=body.readout_ids,
            )
        except Exception as e:
            errors[sym] = str(e)

    return JSONResponse(
        {
            "as_of": as_of.isoformat(),
            "snapshot_id": body.snapshot_id,
            "items": items,
            "errors": errors,
        }
    )


@app.get("/v1/symbol/{symbol}/facts-bundle")
async def symbol_facts_bundle(
    request: Request,
    symbol: str,
    as_of: datetime | None = None,
    latest: bool = False,
    categories: str = "",
    readout_ids: str = "",
    metric_ids: str = "",
    snapshot_id: str | None = None,
    include: str | None = None,
):
    _auth(request)
    if as_of is None and not latest:
        raise HTTPException(422, "as_of is required. Use latest=true for convenience.")
    as_of = (
        datetime.combine(previous_trading_day(_now().date()), datetime.min.time(), tzinfo=UTC)
        if as_of is None
        else _aware(as_of)
    )
    include_set = _parse_include(include)
    con = _get_con()

    from alpha_lake.serving.readouts import compute_readouts

    sections: dict[str, object] = {}
    missing: list[str] = []
    experimental: list[str] = []

    from alpha_lake.transport._shared import _fetch_dataset

    sec_id: str | None = None

    # Price summary
    try:
        from alpha_lake.serving import read_fundamental_metrics_asof
        from alpha_lake.transport._shared import _fetch_bars

        sec_id = resolve_security(con, symbol, as_of=as_of.date())
        if sec_id is not None:
            bars = _fetch_bars(
                con,
                sec_id,
                as_of,
                end=as_of.date(),
                snapshot_id=snapshot_id,
                include_set=include_set,
            )
            if bars:
                sections["price"] = {
                    "last": bars[-1].get("close"),
                    "change": bars[-1].get("change"),
                    "change_pct": bars[-1].get("change_pct"),
                    "volume": bars[-1].get("volume"),
                    "dollar_volume": bars[-1].get("dollar_volume"),
                    "high": max(b.get("high", 0) for b in bars if b.get("high")),
                    "low": min(b.get("low", 0) for b in bars if b.get("low")),
                    "open": bars[-1].get("open"),
                    "latest_date": bars[-1].get("date"),
                }
    except Exception:
        missing.append("price")

    # Readouts
    try:
        sections["readouts"] = compute_readouts(
            con,
            symbol,
            as_of,
            snapshot_id=snapshot_id,
            categories=categories,
            readout_ids=readout_ids,
        )
    except Exception:
        missing.append("readouts")

    # Fundamentals
    try:
        sec_id = resolve_security(con, symbol, as_of=as_of.date())
        if sec_id is not None:
            from alpha_lake.serving import read_fundamental_metrics_asof
            from alpha_lake.transport._shared import _fundamental_row_to_item

            cat_list = (
                [c.strip() for c in categories.split(",") if c.strip()] if categories else None
            )
            mid_list = (
                [m.strip() for m in metric_ids.split(",") if m.strip()] if metric_ids else None
            )
            df = read_fundamental_metrics_asof(
                con,
                security_ids=[sec_id],
                as_of=as_of,
                categories=cat_list,
                metric_ids=mid_list,
                snapshot_id=snapshot_id,
            )
            if not df.is_empty():
                sections["fundamentals"] = {
                    "metrics": [
                        _fundamental_row_to_item(r, include_set) for r in df.rows(named=True)
                    ],
                    "metric_count": len(df),
                }
    except Exception:
        missing.append("fundamentals")

    # Insider transactions
    try:
        if sec_id is not None:
            insider_rows = _fetch_dataset(
                con,
                "insider_tx",
                sec_id,
                as_of,
                snapshot_id=snapshot_id,
                source_precedence_dataset="insider_tx",
                include_set=include_set,
            )
            if insider_rows:
                sections["insider_tx"] = insider_rows
    except Exception:
        missing.append("insider_tx")

    # Earnings events
    try:
        if sec_id is not None:
            import datetime as _dt

            earnings_rows = _fetch_dataset(
                con,
                "earnings_calendar",
                sec_id,
                as_of,
                start=as_of.date() - _dt.timedelta(days=90),
                end=as_of.date(),
                snapshot_id=snapshot_id,
                include_set=include_set,
            )
            if earnings_rows:
                sections["earnings_events"] = earnings_rows
    except Exception:
        missing.append("earnings_events")

    # Attention metrics (experimental)
    try:
        if sec_id is not None:
            import datetime as _dt

            mention_rows = _fetch_dataset(
                con,
                "attention_metrics",
                sec_id,
                as_of,
                start=as_of.date() - _dt.timedelta(days=30),
                end=as_of.date(),
                snapshot_id=snapshot_id,
                include_set=include_set,
            )
            if mention_rows:
                sections["attention_metrics"] = mention_rows
                experimental.append("attention_metrics")
    except Exception:
        pass

    freshness: dict[str, str] = {}
    for section_key, section_data in sections.items():
        if isinstance(section_data, dict):
            for f in ("as_of", "latest_date", "computed_at"):
                val = section_data.get(f)
                if val is not None:
                    freshness[section_key] = str(val)
                    break

    return JSONResponse(
        {
            "symbol": symbol,
            "as_of": as_of.isoformat(),
            "snapshot_id": snapshot_id,
            "sections": sections,
            "freshness": freshness,
            "provenance": {
                "api_version": "v1",
                "contract_version": "1.0.0",
            },
            "metadata": {
                "computed_at": _now().isoformat(),
                "missing_sections": missing,
                "experimental_sections": experimental,
            },
        }
    )


@app.post("/v1/facts-bundle/batch")
async def batch_facts_bundle(request: Request, body: FactsBundleRequest):
    _auth(request)
    if not body.symbols:
        raise HTTPException(422, "At least one symbol is required")
    if body.as_of is None and not body.latest:
        raise HTTPException(
            422, "as_of is required for research reads. Use latest=true for convenience."
        )
    as_of = (
        datetime.combine(previous_trading_day(_now().date()), datetime.min.time(), tzinfo=UTC)
        if body.as_of is None
        else _aware(body.as_of)
    )
    include_set = _parse_include(body.include)
    con = _get_con()

    items: dict[str, object] = {}
    errors: dict[str, str] = {}
    for sym in body.symbols:
        try:
            from alpha_lake.serving.readouts import compute_readouts
            from alpha_lake.transport._shared import _fetch_bars

            sections: dict[str, object] = {}
            missing: list[str] = []
            experimental: list[str] = []

            sec_id = resolve_security(con, sym, as_of=as_of.date())
            if sec_id is not None:
                bars = _fetch_bars(
                    con,
                    sec_id,
                    as_of,
                    end=as_of.date(),
                    snapshot_id=body.snapshot_id,
                    include_set=include_set,
                )
                if bars:
                    sections["price"] = {
                        "last": bars[-1].get("close"),
                        "change": bars[-1].get("change"),
                        "change_pct": bars[-1].get("change_pct"),
                        "volume": bars[-1].get("volume"),
                        "dollar_volume": bars[-1].get("dollar_volume"),
                        "high": max(b.get("high", 0) for b in bars if b.get("high")),
                        "low": min(b.get("low", 0) for b in bars if b.get("low")),
                        "open": bars[-1].get("open"),
                        "latest_date": bars[-1].get("date"),
                    }

            try:
                sections["readouts"] = compute_readouts(
                    con,
                    sym,
                    as_of,
                    snapshot_id=body.snapshot_id,
                    categories=body.categories,
                    readout_ids=body.readout_ids,
                )
            except Exception:
                missing.append("readouts")

            if sec_id is not None:
                try:
                    from alpha_lake.serving import read_fundamental_metrics_asof
                    from alpha_lake.transport._shared import _fundamental_row_to_item

                    cat_list = (
                        [c.strip() for c in body.categories.split(",") if c.strip()]
                        if body.categories
                        else None
                    )
                    mid_list = (
                        [m.strip() for m in body.metric_ids.split(",") if m.strip()]
                        if body.metric_ids
                        else None
                    )
                    df = read_fundamental_metrics_asof(
                        con,
                        security_ids=[sec_id],
                        as_of=as_of,
                        categories=cat_list,
                        metric_ids=mid_list,
                        snapshot_id=body.snapshot_id,
                    )
                    if not df.is_empty():
                        sections["fundamentals"] = {
                            "metrics": [
                                _fundamental_row_to_item(r, include_set)
                                for r in df.rows(named=True)
                            ],
                            "metric_count": len(df),
                        }
                except Exception:
                    missing.append("fundamentals")

                try:
                    import datetime as _dt

                    from alpha_lake.transport._shared import _fetch_dataset

                    insider_rows = _fetch_dataset(
                        con,
                        "insider_tx",
                        sec_id,
                        as_of,
                        snapshot_id=body.snapshot_id,
                        source_precedence_dataset="insider_tx",
                        include_set=include_set,
                    )
                    if insider_rows:
                        sections["insider_tx"] = insider_rows
                    earnings_rows = _fetch_dataset(
                        con,
                        "earnings_calendar",
                        sec_id,
                        as_of,
                        start=as_of.date() - _dt.timedelta(days=90),
                        end=as_of.date(),
                        snapshot_id=body.snapshot_id,
                        include_set=include_set,
                    )
                    if earnings_rows:
                        sections["earnings_events"] = earnings_rows
                except Exception:
                    pass

            items[sym] = {
                "symbol": sym,
                "sections": sections,
                "freshness": {},
                "missing_sections": missing,
                "experimental_sections": experimental,
            }
        except Exception as e:
            errors[sym] = str(e)

    return JSONResponse(
        {
            "as_of": as_of.isoformat(),
            "snapshot_id": body.snapshot_id,
            "items": items,
            "errors": errors,
        }
    )


# ── Symbol Management (authenticated) ──────────────────────────────────────────


class AddSymbolRequest(BaseModel):
    symbol: str


class RemoveSymbolRequest(BaseModel):
    symbol: str


@app.get("/v1/symbols")
async def list_symbols_endpoint(request: Request, active_only: bool = True):
    """List symbols in the registry (active or all)."""
    _auth(request)
    from alpha_lake.flows.bootstrap import list_symbols

    return JSONResponse(list_symbols(active_only=active_only))


@app.post("/v1/symbols")
async def add_symbol_endpoint(request: Request, body: AddSymbolRequest):
    """Add a symbol: backfill STOOQ bars, compute indicators, register."""
    _auth(request)
    con = _get_con()
    from alpha_lake.flows.bootstrap import add_symbol

    try:
        result = add_symbol(con, body.symbol)
        return JSONResponse(result)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@app.delete("/v1/symbols/{symbol}")
async def remove_symbol_endpoint(request: Request, symbol: str):
    """Soft-remove a symbol: hides from UI, stops ingestion."""
    _auth(request)
    from alpha_lake.flows.bootstrap import remove_symbol

    result = remove_symbol(symbol)
    return JSONResponse(result)


# ── Dashboard API router ────────────────────────────────────────────────────

from alpha_lake.transport.dashboard import router as dashboard_router  # noqa: E402

app.include_router(dashboard_router)
