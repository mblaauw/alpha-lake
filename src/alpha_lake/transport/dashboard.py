from __future__ import annotations

from datetime import UTC, date, datetime
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
from alpha_lake.derived import atr, bollinger_bands, ema, macd, rsi, sma
from alpha_lake.security_master import resolve as resolve_security
from alpha_lake.security_master import search as search_securities
from alpha_lake.serving import read_bars_asof

router = APIRouter(prefix="/v1/dashboard")

_INDICATOR_MAP: dict[str, Any] = {
    "sma": sma,
    "ema": ema,
    "rsi": rsi,
    "bollinger": bollinger_bands,
    "atr": atr,
    "macd": macd,
}
_RECURSIVE_MULTIPLIER: dict[str, int] = {
    "sma": 1,
    "ema": 3,
    "rsi": 3,
    "bollinger": 1,
    "atr": 5,
    "macd": 3,
}
_MAX_LOOKBACK_DAYS = 365 * 3


def _check_enabled() -> None:
    if not get_config().transport.dashboard_enabled:
        raise HTTPException(404)


def _get_con():
    return connect(get_config())


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_indicators(spec: str) -> list[tuple[str, list[int | float]]]:
    parts = spec.split(",")
    result: list[tuple[str, list[int | float]]] = []
    for part in parts:
        part = part.strip()
        if ":" in part:
            name, *args_str = part.split(":")
            args = [float(a) for a in args_str]
            result.append((name, args))
        else:
            result.append((part, []))
    return result


def _compute_warmup(
    indicator: str, args: list[int | float], start: date | None, exchange: str = "XNYS"
) -> date | None:
    if start is None:
        return None
    mult = _RECURSIVE_MULTIPLIER.get(indicator, 1)
    window = int(args[0]) if args else 14
    return shift_trading_days(start, -(window * mult), exchange=exchange)


def _pl_to_dicts(df: pl.DataFrame) -> list[dict[str, Any]]:
    return [{k: _v(v) for k, v in row.items()} for row in df.rows(named=True)]


def _v(val: Any) -> Any:
    if isinstance(val, datetime | date):
        return val.isoformat()
    return val


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
