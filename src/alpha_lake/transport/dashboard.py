from __future__ import annotations

from datetime import date, datetime
from typing import Any

import polars as pl  # type: ignore[unresolved-import]
from fastapi import APIRouter, HTTPException  # type: ignore[unresolved-import]
from fastapi.responses import JSONResponse  # type: ignore[unresolved-import]

from alpha_lake.calendar_ import shift_trading_days
from alpha_lake.catalog import (
    catalog_health,
    connect,
    dataset_health,
    list_datasets,
    list_snapshots,
)
from alpha_lake.config import get_config
from alpha_lake.derived import atr, macd, rsi, sma
from alpha_lake.derived.event_aggregations import (
    compute_attention_deltas,
    compute_sentiment_ratios,
)
from alpha_lake.security_master import resolve as resolve_security
from alpha_lake.security_master import search as search_securities
from alpha_lake.serving import pit_read, read_bars_adjusted, read_bars_asof, read_macro_series_asof
from alpha_lake.transport._shared import (
    _INDICATOR_MAP,
    _MAX_LOOKBACK_DAYS,
    _compute_warmup,
    _now,
    _parse_indicators,
    _pl_to_dicts,
)

router = APIRouter(prefix="/v1/dashboard")


def _check_enabled() -> None:
    if not get_config().transport.dashboard_enabled:
        raise HTTPException(404)


def _get_con():
    return connect(get_config())


# ── Health ────────────────────────────────────────────────────────────────────


@router.get("/health")
async def health():
    _check_enabled()
    return catalog_health(_get_con())


# ── Datasets ──────────────────────────────────────────────────────────────────


@router.get("/datasets")
async def datasets():
    _check_enabled()
    con = _get_con()
    cfg = get_config()
    all_ds = list_datasets(con)
    result = []
    for ds in all_ds:
        name = str(ds["dataset"])
        hlth = dataset_health(con, name)
        posture = cfg.datasets.get(name)
        result.append(
            {
                "dataset": name,
                "tier": posture.tier if posture else "unknown",
                "supported": posture.supported if posture else False,
                "sla": posture.sla if posture else False,
                "rows": hlth.get("rows", 0),
                "latest_effective_date": str(hlth.get("latest_date", "")),
                "status": hlth.get("status", "unknown"),
                "schema_version": ds.get("schema_version", 0),
            }
        )
    con.close()
    return result


@router.get("/dataset/{name}")
async def dataset_detail(
    name: str,
    limit: int = 50,
    as_of: datetime | None = None,
):
    _check_enabled()
    con = _get_con()
    names = {str(d["dataset"]) for d in list_datasets(con)}
    if name not in names:
        con.close()
        raise HTTPException(404, f"Dataset '{name}' not found")
    cap = min(limit, 500)
    as_of_filter = ""
    if as_of:
        as_of_filter = f" WHERE available_at <= TIMESTAMP '{as_of.isoformat()}'"
    query = (
        f"SELECT * FROM {name}{as_of_filter} ORDER BY effective_date DESC NULLS LAST LIMIT {cap}"
    )
    try:
        rows = con.execute(query).fetchall()
        cols = [c[0] for c in con.execute(f"DESCRIBE {name}").fetchall()]
        result = [dict(zip(cols, r, strict=False)) for r in rows]
    except Exception:
        cols = []
        result = []
    con.close()
    return {
        "dataset": name,
        "columns": cols,
        "rows": result,
        "fetched_at": _now().isoformat(),
    }


# ── Securities ────────────────────────────────────────────────────────────────


@router.get("/securities")
async def securities(
    q: str = "",
    limit: int = 20,
    as_of: date | None = None,
):
    _check_enabled()
    if not q:
        return []
    con = _get_con()
    results = search_securities(con, q, limit=limit, as_of=as_of)
    con.close()
    return results


@router.get("/security/{symbol}")
async def security_detail(
    symbol: str,
    as_of: datetime | None = None,
):
    _check_enabled()
    if as_of is None:
        as_of = _now()
    con = _get_con()
    sec_id = resolve_security(con, symbol, as_of=as_of.date())
    if sec_id is None:
        con.close()
        raise HTTPException(404, f"Symbol '{symbol}' not found")

    agg: dict[str, Any] = {
        "symbol": symbol,
        "security_id": sec_id,
        "as_of": as_of.isoformat(),
        "datasets": {},
    }

    for ds_name in list_datasets(con):
        ds_name_str = str(ds_name["dataset"])
        try:
            cols_row = con.execute(f"DESCRIBE {ds_name_str}").fetchall()
            id_col = "security_id" if ds_name_str != "macro_series" else "series_id"
            query = (
                f"SELECT * FROM {ds_name_str} WHERE {id_col} = ?"
                f" AND available_at <= ? ORDER BY effective_date DESC LIMIT 10"
            )
            rows = con.execute(
                query,
                [sec_id, as_of],
            ).fetchall()
            if rows:
                col_names = [c[0] for c in cols_row]
                agg["datasets"][ds_name_str] = [dict(zip(col_names, r, strict=False)) for r in rows]
        except Exception:
            pass
    con.close()
    return agg


# ── Snapshots ─────────────────────────────────────────────────────────────────


@router.get("/snapshots")
async def snapshots():
    _check_enabled()
    con = _get_con()
    result = list_snapshots(con)
    con.close()
    return result


# ── Bars ──────────────────────────────────────────────────────────────────────


@router.get("/bars")
async def bars(
    symbol: str,
    start: date | None = None,
    end: date | None = None,
    as_of: datetime | None = None,
    snapshot_id: str | None = None,
    price_mode: str = "raw",
):
    _check_enabled()

    if as_of is None:
        as_of = _now()

    if start and end and (end - start).days > _MAX_LOOKBACK_DAYS:
        raise HTTPException(422, f"Lookback exceeds max of {_MAX_LOOKBACK_DAYS} days")

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


@router.get("/bars/indicators")
async def bars_indicators(
    symbol: str,
    indicators: str,
    start: date | None = None,
    end: date | None = None,
    as_of: datetime | None = None,
):
    _check_enabled()

    if as_of is None:
        as_of = _now()

    if start and end and (end - start).days > _MAX_LOOKBACK_DAYS:
        raise HTTPException(422, f"Lookback exceeds max of {_MAX_LOOKBACK_DAYS} days")

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


# ── Per-symbol card bundle ─────────────────────────────────────────────────


@router.get("/bars/summary")
async def bars_summary(
    symbol: str,
    as_of: datetime | None = None,
    price_mode: str = "raw",
):
    _check_enabled()
    if as_of is None:
        as_of = _now()
    con = _get_con()
    sec_id = resolve_security(con, symbol, as_of=as_of.date())
    if sec_id is None:
        sec_id = symbol  # fallback: use symbol as security_id (synthetic path)
    start = shift_trading_days(as_of.date(), -180)
    kwargs: dict[str, Any] = {"security_ids": [sec_id], "as_of": as_of, "start_date": start}
    if price_mode != "raw":
        kwargs["price_mode"] = price_mode
    df = read_bars_adjusted(con, **kwargs) if price_mode != "raw" else read_bars_asof(con, **kwargs)
    con.close()
    if df.height < 1:
        raise HTTPException(404, f"No bars for '{symbol}'")

    df = df.sort("effective_date")
    close, high, low, vol = df["close"], df["high"], df["low"], df["volume"]
    last = float(close[-1])
    prev = float(close[-2]) if df.height >= 2 else last

    def _last(series) -> float | None:
        for x in reversed(list(series)):
            if x is not None:
                return float(x)
        return None

    macd_bands = macd(close)
    mean_vol_20d = sum(vol.tail(20)) / max(len(vol.tail(20)), 1)
    summary: dict[str, Any] = {
        "symbol": symbol,
        "security_id": sec_id,
        "last": last,
        "change_pct": (last / prev - 1) * 100 if prev else 0.0,
        "rsi": _last(rsi(close, 14)),
        "sma50": _last(sma(close, 50)),
        "atr": _last(atr(high, low, close, 14)),
        "macd": _last(macd_bands.get("macd")) if isinstance(macd_bands, dict) else None,
        "vol_ratio": (float(vol[-1]) / (float(mean_vol_20d) or 1.0))
        if vol[-1] is not None
        else None,
        "latest_date": str(df["effective_date"][-1]),
        "quality_status": df["quality_status"][-1] if "quality_status" in df.columns else "valid",
        "source_id": df["source_id"][-1] if "source_id" in df.columns else None,
        "trend": [float(c) for c in close.tail(120) if c is not None],
    }
    return JSONResponse(summary)


# ── Attention + Sentiment leaderboard ──────────────────────────────────────


_SYMBOL_CACHE: dict[str, str] = {}
_SYMBOL_CACHE_MAX = 10000


def _symbol_for(con, security_id: str, as_of: datetime) -> str | None:
    if security_id in _SYMBOL_CACHE:
        return _SYMBOL_CACHE[security_id]
    try:
        row = con.execute(
            "SELECT symbol FROM security_master "
            "WHERE security_id = ? AND effective_start <= ? "
            "ORDER BY effective_start DESC LIMIT 1",
            [security_id, as_of.date()],
        ).fetchone()
    except Exception:
        row = None
    sym = row[0] if row else None
    if sym:
        if len(_SYMBOL_CACHE) >= _SYMBOL_CACHE_MAX:
            _SYMBOL_CACHE.clear()
        _SYMBOL_CACHE[security_id] = sym
    return sym


@router.get("/attention/leaderboard")
async def attention_leaderboard(limit: int = 20, as_of: datetime | None = None):
    _check_enabled()
    if as_of is None:
        as_of = _now()
    con = _get_con()

    try:
        att = con.execute("SELECT * FROM attention_metrics WHERE available_at <= ?", [as_of]).pl()
        sent = con.execute(
            "SELECT * FROM sentiment_annotations WHERE available_at <= ?", [as_of]
        ).pl()
    except Exception:
        con.close()
        return JSONResponse([])

    if att.height == 0:
        con.close()
        return JSONResponse([])

    deltas = compute_attention_deltas(att, as_of)
    ratios = compute_sentiment_ratios(sent, as_of) if sent.height > 0 else None

    latest_att = (
        att.sort("effective_date")
        .group_by("security_id")
        .agg(
            pl.col("mentions").last().alias("mentions"),
            pl.col("rank").last().alias("rank"),
            pl.col("cohort").last().alias("cohort"),
        )
    )
    latest_delta = (
        deltas.sort("effective_date")
        .group_by("security_id")
        .agg(pl.col("mention_delta_pct").last())
        if deltas.height > 0
        else None
    )
    latest_ratio = (
        ratios.sort("effective_date")
        .group_by("security_id")
        .agg(
            pl.col("positive_ratio").last(),
            pl.col("mean_score").last(),
            pl.col("total_messages").last(),
        )
        if (ratios is not None and ratios.height > 0)
        else None
    )

    board = latest_att
    if latest_delta is not None:
        board = board.join(latest_delta, on="security_id", how="left")
    if latest_ratio is not None:
        board = board.join(latest_ratio, on="security_id", how="left")
    board = board.sort("mentions", descending=True).head(limit)

    trends: dict[str, list[float]] = {}
    for sid in board["security_id"]:
        s = att.filter(pl.col("security_id") == sid).sort("effective_date").tail(30)
        trends[sid] = [float(m) for m in s["mentions"] if m is not None]

    rows: list[dict[str, Any]] = []
    for r in board.iter_rows(named=True):
        sid = r["security_id"]
        rows.append(
            {
                "security_id": sid,
                "symbol": _symbol_for(con, sid, as_of) or str(sid),
                "name": "",
                "mentions": int(r["mentions"]) if r["mentions"] is not None else 0,
                "rank": r.get("rank"),
                "cohort": r.get("cohort"),
                "mention_delta_pct": r.get("mention_delta_pct"),
                "positive_ratio": r.get("positive_ratio"),
                "mean_score": r.get("mean_score"),
                "total_messages": r.get("total_messages"),
                "trend": trends.get(sid, []),
            }
        )
    con.close()
    return JSONResponse(rows)


# ── Macro series ──────────────────────────────────────────────────────────


@router.get("/macro/{series_id}")
async def macro_series(
    series_id: str,
    as_of: datetime | None = None,
    start: date | None = None,
    end: date | None = None,
):
    _check_enabled()
    if as_of is None:
        as_of = _now()
    con = _get_con()
    df = read_macro_series_asof(
        con,
        series_ids=[series_id],
        as_of=as_of,
        start_date=start,
        end_date=end,
    )
    con.close()
    if df.is_empty():
        return JSONResponse([])
    df = df.sort("effective_date", descending=True)
    return JSONResponse(_pl_to_dicts(df))


# ── Insider transactions ──────────────────────────────────────────────────


@router.get("/insider/{symbol}")
async def insider_tx(symbol: str, as_of: datetime | None = None, limit: int = 50):
    _check_enabled()
    if as_of is None:
        as_of = _now()
    con = _get_con()
    sec_id = resolve_security(con, symbol, as_of=as_of.date())
    if sec_id is None:
        sec_id = symbol
    df = pit_read(con, table="insider_tx", security_ids=[sec_id], as_of=as_of)
    con.close()
    if df.is_empty():
        return JSONResponse([])
    df = df.sort("effective_date", descending=True).head(min(limit, 500))
    return JSONResponse(_pl_to_dicts(df))


# ── Analyst estimates ─────────────────────────────────────────────────────


@router.get("/analyst/{symbol}")
async def analyst_estimates(symbol: str, as_of: datetime | None = None, limit: int = 50):
    _check_enabled()
    if as_of is None:
        as_of = _now()
    con = _get_con()
    sec_id = resolve_security(con, symbol, as_of=as_of.date())
    if sec_id is None:
        sec_id = symbol
    df = pit_read(con, table="analyst_estimates", security_ids=[sec_id], as_of=as_of)
    con.close()
    if df.is_empty():
        return JSONResponse([])
    df = df.sort("effective_date", descending=True).head(min(limit, 500))
    return JSONResponse(_pl_to_dicts(df))
