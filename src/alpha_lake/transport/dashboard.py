from __future__ import annotations

import contextlib
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb  # type: ignore[unresolved-import]
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
from alpha_lake.derived import atr, bollinger_bands, macd, rsi, sma
from alpha_lake.derived.event_aggregations import (
    compute_attention_deltas,
    compute_sentiment_ratios,
)
from alpha_lake.derived.indicators import (
    atr_pct,
    avg_dollar_volume,
    dollar_volume,
    ema,
    gap_pct,
    is_new_high,
    is_new_low,
    obv,
    pct_off_high,
    pct_off_low,
    realized_vol,
    relative_volume,
    returns,
    vwap,
)
from alpha_lake.interpretation import READOUTS
from alpha_lake.interpretation.profiles import load_threshold_profiles
from alpha_lake.interpretation.readouts import (
    compute_all_readouts,
    warmup_bars_needed,
)
from alpha_lake.security_master import resolve as resolve_security
from alpha_lake.security_master import search as search_securities
from alpha_lake.serving import pit_read, read_bars_adjusted, read_bars_asof, read_macro_series_asof
from alpha_lake.transport._glossary import _GLOSSARY
from alpha_lake.transport._models import (
    BarsSummaryResponse,
    DatasetDetailResponse,
    DatasetInfo,
    HealthResponse,
    LeaderboardRow,
    ReadoutsResponse,
    SymbolInfo,
    TransactionRow,
)
from alpha_lake.transport._shared import (
    _INDICATOR_MAP,
    _MAX_LOOKBACK_DAYS,
    _compute_warmup,
    _now,
    _parse_indicators,
    _pl_to_dicts,
    _serialize_bars_df,
    _validate_price_mode,
)

router = APIRouter(prefix="/v1/dashboard")


_connection: duckdb.DuckDBPyConnection | None = None


def _check_enabled() -> None:
    if not get_config().transport.dashboard_enabled:
        raise HTTPException(404)


def _get_con() -> duckdb.DuckDBPyConnection:
    global _connection
    if _connection is None:
        _connection = connect(get_config())
    try:
        _connection.execute("SELECT 1")
    except Exception:
        _connection = connect(get_config())
    return _connection


def _aware(dt: datetime) -> datetime:
    """Normalize a datetime to tz-aware UTC for TIMESTAMPTZ comparisons.

    ``available_at`` columns are stored as TIMESTAMPTZ (the connection runs in
    UTC). Passing a naive datetime into a raw ``?`` parameter mixes types; this
    guarantees a tz-aware value so every comparison casts to ``::TIMESTAMPTZ``
    cleanly.
    """
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


# ── Health ────────────────────────────────────────────────────────────────────


@router.get("/health", response_model=HealthResponse)
async def health():
    _check_enabled()
    hlth = catalog_health(_get_con())
    hlth["synthetic_mode"] = get_config().lake.synthetic_mode
    return hlth


# ── Datasets ──────────────────────────────────────────────────────────────────


@router.get("/datasets", response_model=list[DatasetInfo])
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
    return result


@router.get("/dataset/{name}", response_model=DatasetDetailResponse)
async def dataset_detail(
    name: str,
    limit: int = 50,
    as_of: datetime | None = None,
):
    _check_enabled()
    con = _get_con()
    names = {str(d["dataset"]) for d in list_datasets(con)}
    if name not in names:
        raise HTTPException(404, f"Dataset '{name}' not found")
    cap = min(limit, 500)
    where = ""
    params: list[Any] = []
    if as_of:
        where = " WHERE available_at <= ?::TIMESTAMPTZ"
        params = [_aware(as_of)]
    query = f'SELECT * FROM "{name}"{where} ORDER BY effective_date DESC NULLS LAST LIMIT {cap}'
    try:
        rows = con.execute(query, params).fetchall()
        cols = [c[0] for c in con.execute(f'DESCRIBE "{name}"').fetchall()]
        result = [dict(zip(cols, r, strict=False)) for r in rows]
    except Exception:
        cols = []
        result = []
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
    return results


@router.get("/security/{symbol}")
async def security_detail(
    symbol: str,
    as_of: datetime | None = None,
    datasets: str = "",
):
    """Per-symbol aggregation across datasets.

    ``datasets`` is an optional comma-separated allow-list. The Bars cards pass
    only the cross-dataset signals they render (insider/sentiment/news/attention),
    so we scan ~4 tables instead of all ~18 — a large win on the Bars tab where
    this is called once per card.

    When omitted all datasets are scanned — use the allow-list in production.
    """
    _check_enabled()
    if as_of is None:
        as_of = _now()
    con = _get_con()
    sec_id = resolve_security(con, symbol, as_of=as_of.date())
    if sec_id is None:
        sec_id = symbol

    wanted = {d.strip() for d in datasets.split(",") if d.strip()} if datasets else None

    agg: dict[str, Any] = {
        "symbol": symbol,
        "security_id": sec_id,
        "as_of": as_of.isoformat(),
        "datasets": {},
    }

    for ds_name in list_datasets(con):
        ds_name_str = str(ds_name["dataset"])
        if wanted is not None and ds_name_str not in wanted:
            continue
        try:
            cols_row = con.execute(f'DESCRIBE "{ds_name_str}"').fetchall()
            id_col = "security_id" if ds_name_str != "macro_series" else "series_id"
            query = (
                f'SELECT * FROM "{ds_name_str}" WHERE {id_col} = ?'
                f" AND available_at <= ?::TIMESTAMPTZ ORDER BY effective_date DESC LIMIT 10"
            )
            rows = con.execute(
                query,
                [sec_id, _aware(as_of)],
            ).fetchall()
            if rows:
                col_names = [c[0] for c in cols_row]
                agg["datasets"][ds_name_str] = [dict(zip(col_names, r, strict=False)) for r in rows]
        except Exception:
            pass
    return agg


# ── Snapshots ─────────────────────────────────────────────────────────────────


@router.get("/snapshots")
async def snapshots():
    _check_enabled()
    con = _get_con()
    result = list_snapshots(con)
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

    _validate_price_mode(price_mode)
    sec_id = resolve_security(_get_con(), symbol, as_of=as_of.date())

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
    result = _serialize_bars_df(bars_df)

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
        mask = [str(d) >= start.isoformat() for d in bars_df["effective_date"].to_list()]
        for key in list(result.keys()):
            result[key] = [v for v, m in zip(result[key], mask, strict=True) if m]

    return JSONResponse(result)


# ── Readouts ──────────────────────────────────────────────────────────────


@router.get("/symbol/{symbol}/readouts", response_model=ReadoutsResponse)
async def symbol_readouts(
    symbol: str,
    as_of: datetime | None = None,
    latest: bool = False,
    categories: str = "",
    readout_ids: str = "",
):
    _check_enabled()
    con = _get_con()
    cfg = get_config()

    if as_of is None and not latest:
        raise HTTPException(
            422,
            "as_of is required for point-in-time reads. "
            "Use latest=true for the most recent observation.",
        )

    as_of = _now() if as_of is None else _aware(as_of)

    sec_id = resolve_security(con, symbol, as_of=as_of.date())
    if sec_id is None:
        sec_id = symbol

    warmup = warmup_bars_needed()
    start = shift_trading_days(as_of.date(), -warmup)

    # Fetch bars
    bars_df = read_bars_asof(
        con,
        security_ids=[sec_id],
        as_of=as_of,
        start_date=start,
    )
    if bars_df.is_empty():
        return JSONResponse(
            {
                "symbol": symbol,
                "as_of": as_of.isoformat(),
                "readouts": [],
                "metadata": {
                    "computed_at": _now().isoformat(),
                    "bars_available": 0,
                    "readouts_computed": 0,
                    "readouts_unavailable": 0,
                },
            }
        )
    bars_df = bars_df.sort("effective_date")

    # Fetch stored indicators if available
    indicators_df: pl.DataFrame | None = None
    with contextlib.suppress(Exception):
        indicators_df = con.execute(
            "SELECT * FROM technical_indicators"
            " WHERE security_id = ? AND available_at <= ?::TIMESTAMPTZ"
            " ORDER BY effective_date ASC",
            [sec_id, _aware(as_of)],
        ).pl()

    # Fetch benchmark bars if needed
    benchmark = cfg.readouts.benchmark_symbol
    benchmark_df: pl.DataFrame | None = None
    if any("benchmark_bars" in r.source_requirements for r in READOUTS.values()):
        bm_id = resolve_security(con, benchmark, as_of=as_of.date())
        if bm_id is not None:
            with contextlib.suppress(Exception):
                benchmark_df = read_bars_asof(
                    con,
                    security_ids=[bm_id],
                    as_of=as_of,
                    start_date=start,
                )
                if not benchmark_df.is_empty():
                    benchmark_df = benchmark_df.sort("effective_date")

    # Load profiles
    profile_path = Path(cfg.readouts.profile_file)
    if not profile_path.exists():
        return JSONResponse(
            {
                "symbol": symbol,
                "as_of": as_of.isoformat(),
                "readouts": [],
                "metadata": {
                    "computed_at": _now().isoformat(),
                    "bars_available": len(bars_df),
                    "readouts_computed": 0,
                    "readouts_unavailable": 0,
                    "error": f"Profile file not found: {profile_path}",
                },
            }
        )
    profiles = load_threshold_profiles(profile_path)

    # Compute
    observations = compute_all_readouts(
        bars=bars_df,
        indicators=indicators_df,
        benchmark_bars=benchmark_df,
        as_of=as_of,
        profiles=profiles,
    )

    # Filter
    if categories:
        wanted_cats = {c.strip() for c in categories.split(",")}
        observations = [
            o
            for o in observations
            if (defn := READOUTS.get(o.definition_id)) is not None and defn.category in wanted_cats
        ]
    if readout_ids:
        wanted_ids = {r.strip() for r in readout_ids.split(",")}
        observations = [o for o in observations if o.definition_id in wanted_ids]

    # Merge definitions + observations
    readouts_json = []
    for obs in observations:
        defn = READOUTS.get(obs.definition_id)
        if defn is None:
            continue
        readouts_json.append(
            {
                "definition": {
                    "definition_id": defn.definition_id,
                    "name": defn.name,
                    "category": defn.category,
                    "source_requirements": defn.source_requirements,
                    "surface": defn.surface,
                    "description": defn.description,
                    "question": defn.question,
                    "calculation_formula": defn.calculation_formula,
                    "lookback_bars": defn.lookback_bars,
                    "parameters": defn.parameters,
                    "threshold_profile_id": defn.threshold_profile_id,
                    "display_value_type": defn.display_value_type,
                    "display_decimals": defn.display_decimals,
                    "display_suffix": defn.display_suffix,
                    "display_primary_label": defn.display_primary_label,
                    "display_secondary_label": defn.display_secondary_label,
                },
                "observation": obs.to_dict(),
            }
        )

    n_unavail = sum(1 for o in observations if o.state == "unavailable")
    return JSONResponse(
        {
            "symbol": symbol,
            "as_of": as_of.isoformat(),
            "readouts": readouts_json,
            "metadata": {
                "computed_at": _now().isoformat(),
                "bars_available": len(bars_df),
                "readouts_computed": len(observations),
                "readouts_unavailable": n_unavail,
            },
        }
    )


# ── Symbols with real data (replaces hardcoded WATCHLIST) ────────────────


@router.get("/bars/symbols", response_model=list[SymbolInfo])
async def bars_symbols():
    """Return distinct symbols that have data in the lake.

    Scans price/indicator tables FIRST (``lake_bars`` is the canonical source
    for "symbols with bars" — the Bars tab is a price view), then the social
    tables so attention-only names still surface. De-duplicated by security_id.
    """
    _check_enabled()
    con = _get_con()
    seen: dict[str, dict[str, str]] = {}
    for table, id_col in [
        ("lake_bars", "security_id"),
        ("technical_indicators", "security_id"),
        ("attention_metrics", "security_id"),
        ("sentiment_annotations", "security_id"),
        ("insider_tx", "security_id"),
    ]:
        try:
            ids = con.execute(
                f"SELECT DISTINCT {id_col} FROM {table}"
                f" WHERE {id_col} IS NOT NULL AND {id_col} != '' LIMIT 200"
            ).fetchall()
            for row in ids:
                sid = str(row[0])
                if sid and sid not in seen:
                    sym, name = _symbol_name_for(con, sid, _now())
                    seen[sid] = {"security_id": sid, "symbol": sym or sid, "name": name or ""}
        except Exception:
            pass
    result = list(seen.values())
    result.sort(key=lambda x: x["symbol"])
    return JSONResponse(result)


# ── Per-symbol card bundle ─────────────────────────────────────────────────


# Model column names whose values are boolean
_BOOL_INDICATOR_COLS = frozenset(
    {
        "is_new_52w_high",
        "is_new_52w_low",
        "above_ma_20",
        "above_ma_50",
        "above_ma_200",
        "volume_spike",
        "bb_squeeze",
        "inside_bar",
        "outside_bar",
        "gap_fill",
    }
)


@router.get("/bars/summary", response_model=BarsSummaryResponse)
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
    start = shift_trading_days(as_of.date(), -180)
    kwargs: dict[str, Any] = {"security_ids": [sec_id], "as_of": as_of, "start_date": start}
    if price_mode != "raw":
        kwargs["price_mode"] = price_mode
    df = read_bars_adjusted(con, **kwargs) if price_mode != "raw" else read_bars_asof(con, **kwargs)
    if df.height < 1:
        raise HTTPException(404, f"No bars for '{symbol}'")

    df = df.sort("effective_date")
    close, high, low, vol = df["close"], df["high"], df["low"], df["volume"]
    last = float(close[-1])
    prev = float(close[-2]) if (df.height >= 2 and close[-2] is not None) else last

    def _last(series) -> float | None:
        for x in reversed(list(series)):
            if x is not None:
                return float(x)
        return None

    # aligned trend + volume series
    pairs = [
        (c, v)
        for c, v in zip(list(close.tail(120)), list(vol.tail(120)), strict=False)
        if c is not None
    ]
    sym_disp, name_disp = _symbol_name_for(con, sec_id, as_of)

    summary: dict[str, Any] = {
        "symbol": symbol,
        "security_id": sec_id,
        "name": name_disp or "",
        "last": last,
        "change_pct": (last / prev - 1) * 100 if prev else 0.0,
        "latest_date": str(df["effective_date"][-1]),
        "quality_status": df["quality_status"][-1] if "quality_status" in df.columns else "valid",
        "source_id": df["source_id"][-1] if "source_id" in df.columns else None,
        "trend": [float(c) for c, _ in pairs],
        "volume": [float(v) if v is not None else 0.0 for _, v in pairs],
    }

    # ── Try reading from stored technical_indicators first ──────────────
    try:
        _raw = con.execute(
            "SELECT * FROM technical_indicators"
            " WHERE security_id = ? AND available_at <= ?::TIMESTAMPTZ"
            " ORDER BY effective_date DESC, available_at DESC LIMIT 1",
            [sec_id, _aware(as_of)],
        ).pl()
    except Exception:
        _raw = None
    if _raw is not None and _raw.height > 0:
        _store_indicators_into(summary, _raw.row(0, named=True))
        return JSONResponse(summary)

    # ── Fall back to on-the-fly computation ─────────────────────────────
    macd_bands = macd(close)
    bb = bollinger_bands(close)
    open_ = df["open"]
    atr_series = atr(high, low, close, 14)
    sma20 = sma(close, 20)
    sma50 = sma(close, 50)
    sma200 = sma(close, 200)
    ema12 = ema(close, 12)
    ema26 = ema(close, 26)
    rsi14 = rsi(close, 14)
    vol_tail20 = vol.tail(20).drop_nulls()
    _vmean = vol_tail20.mean()
    mean_vol_20d = _vmean if vol_tail20.len() > 0 and isinstance(_vmean, (int, float)) else 0.0
    last_vol = float(vol[-1]) if vol[-1] is not None else None

    summary.update(
        {
            "sma_20": _last(sma20),
            "sma_50": _last(sma50),
            "sma_200": _last(sma200),
            "ema_12": _last(ema12),
            "ema_26": _last(ema26),
            "rsi": _last(rsi14),
            "macd": _last(macd_bands.get("macd")) if isinstance(macd_bands, dict) else None,
            "macd_ema": _last(macd_bands.get("macd_ema")) if isinstance(macd_bands, dict) else None,
            "macd_hist": _last(macd_bands.get("histogram"))
            if isinstance(macd_bands, dict)
            else None,
            "bb_upper": _last(bb.get("upper")) if isinstance(bb, dict) else None,
            "bb_middle": _last(bb.get("middle")) if isinstance(bb, dict) else None,
            "bb_lower": _last(bb.get("lower")) if isinstance(bb, dict) else None,
            "atr": _last(atr_series),
            "atr_pct": _last(atr_pct(atr_series, close)),
            "obv": _last(obv(close, vol)),
            "vwap": _last(vwap(high, low, close, vol)),
            "vol_ratio": (last_vol / mean_vol_20d)
            if (last_vol is not None and mean_vol_20d)
            else None,
            "dollar_volume": _last(dollar_volume(close, vol)),
            "avg_dollar_volume_20": _last(avg_dollar_volume(close, vol, 20)),
            "rvol": _last(relative_volume(vol, 20)),
            "return_1d": _last(returns(close, 1)),
            "return_5d": _last(returns(close, 5)),
            "return_21d": _last(returns(close, 21)),
            "return_63d": _last(returns(close, 63)),
            "gap_pct": _last(gap_pct(open_, close)),
            "pct_off_52w_high": _last(pct_off_high(close, high, 252)),
            "pct_off_52w_low": _last(pct_off_low(close, low, 252)),
            "is_new_52w_high": bool(_last(is_new_high(high, 252)))
            if _last(is_new_high(high, 252)) is not None
            else None,
            "is_new_52w_low": bool(_last(is_new_low(low, 252)))
            if _last(is_new_low(low, 252)) is not None
            else None,
            "realized_vol_21": _last(realized_vol(close, 21)),
            "realized_vol_63": _last(realized_vol(close, 63)),
        }
    )
    return JSONResponse(summary)


def _store_indicators_into(summary: dict[str, Any], row: dict[str, Any]) -> None:
    """Copy stored indicator values from a row dict into *summary*."""
    _model_to_dash: dict[str, str] = {
        "rsi_14": "rsi",
        "atr_14": "atr",
        "macd_histogram": "macd_hist",
        "return_1": "return_1d",
        "return_5": "return_5d",
        "return_21": "return_21d",
        "return_63": "return_63d",
    }
    for col, val in row.items():
        if col in (
            "effective_date",
            "available_at",
            "security_id",
            "source_id",
            "version_hash",
            "content_hash",
            "source_fetch_id",
            "raw_payload_hash",
            "ingestion_run_id",
            "schema_version",
            "parser_version",
            "quality_status",
            "normalization_version",
        ):
            continue
        dst = _model_to_dash.get(col, col)
        if val is None or val == "":
            summary[dst] = None
        elif col in _BOOL_INDICATOR_COLS:
            summary[dst] = bool(val)
        elif isinstance(val, (int, float)):
            summary[dst] = float(val)
        else:
            summary[dst] = val


# ── Attention + Sentiment leaderboard ──────────────────────────────────────


_SYMBOL_CACHE: dict[str, tuple[str | None, str | None]] = {}
_SYMBOL_CACHE_MAX = 10000


def _symbol_name_for(con, security_id: str, as_of: datetime) -> tuple[str | None, str | None]:
    """Reverse-resolve security_id → (symbol, display name), cached."""
    if security_id in _SYMBOL_CACHE:
        return _SYMBOL_CACHE[security_id]
    sym: str | None = None
    name: str | None = None
    try:
        row = con.execute(
            "SELECT symbol, name FROM security_master "
            "WHERE security_id = ? AND effective_start <= ? "
            "ORDER BY effective_start DESC LIMIT 1",
            [security_id, as_of.date()],
        ).fetchone()
        if row:
            sym, name = row[0], row[1]
    except Exception:
        pass
    if sym:
        if len(_SYMBOL_CACHE) >= _SYMBOL_CACHE_MAX:
            _SYMBOL_CACHE.clear()
        _SYMBOL_CACHE[security_id] = (sym, name)
    return sym, name


def _sentiment_split(sent: pl.DataFrame, sids: list[str]) -> dict[str, dict[str, float]]:
    """Real bullish/bearish/neutral ratios from raw labels, latest day per symbol.

    ``compute_sentiment_ratios`` only exposes ``positive_ratio``; here we read
    ``sentiment_label`` directly (same field it keys off) to recover the full
    three-way split instead of fabricating neutral/negative on the client.
    """
    split: dict[str, dict[str, float]] = {}
    if sent.height == 0 or "sentiment_label" not in sent.columns:
        return split
    try:
        lab = pl.col("sentiment_label").str.to_lowercase()
        latest = (
            sent.sort("effective_date")
            .group_by("security_id")
            .agg(pl.col("effective_date").max().alias("_ed"))
        )
        sj = sent.join(latest, on="security_id").filter(pl.col("effective_date") == pl.col("_ed"))
        for sid in sids:
            d = sj.filter(pl.col("security_id") == sid)
            total = d.height
            if total == 0:
                continue
            bull = d.filter(lab.str.contains("bullish", literal=True)).height
            bear = d.filter(lab.str.contains("bearish", literal=True)).height
            neu = max(total - bull - bear, 0)
            split[sid] = {
                "positive_ratio": bull / total,
                "negative_ratio": bear / total,
                "neutral_ratio": neu / total,
                "total_messages": float(total),
            }
    except Exception:
        return {}
    return split


@router.get("/attention/leaderboard", response_model=list[LeaderboardRow])
async def attention_leaderboard(limit: int = 20, as_of: datetime | None = None):
    _check_enabled()
    if as_of is None:
        as_of = _now()
    con = _get_con()

    try:
        att = con.execute(
            "SELECT * FROM attention_metrics WHERE available_at <= ?::TIMESTAMPTZ", [_aware(as_of)]
        ).pl()
    except Exception:
        att = pl.DataFrame()
    try:
        sent = con.execute(
            "SELECT * FROM sentiment_annotations WHERE available_at <= ?::TIMESTAMPTZ",
            [_aware(as_of)],
        ).pl()
    except Exception:
        sent = pl.DataFrame()

    if att.height == 0:
        return JSONResponse([])

    deltas = compute_attention_deltas(att, as_of)
    ratios = compute_sentiment_ratios(sent, as_of) if sent.height > 0 else None

    has_upvotes = "upvotes" in att.columns
    latest_att = (
        att.sort("effective_date")
        .group_by("security_id")
        .agg(
            pl.col("mentions").last().alias("mentions"),
            pl.col("rank").last().alias("rank"),
            pl.col("cohort").last().alias("cohort"),
            pl.col("upvotes").last().alias("upvotes")
            if has_upvotes
            else pl.lit(None).alias("upvotes"),
        )
    )
    latest_delta = (
        deltas.sort("effective_date")
        .group_by("security_id")
        .agg(
            pl.col("mention_delta_pct").last(),
            pl.col("upvote_ratio").last(),
            pl.col("upvote_delta_pct").last(),
        )
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

    board_sids = [str(s) for s in board["security_id"]]
    split = _sentiment_split(sent, board_sids)

    trends: dict[str, list[float]] = {}
    for sid in board["security_id"]:
        s = att.filter(pl.col("security_id") == sid).sort("effective_date").tail(30)
        trends[str(sid)] = [float(m) for m in s["mentions"] if m is not None]

    rows: list[dict[str, Any]] = []
    for r in board.iter_rows(named=True):
        sid = str(r["security_id"])
        sym, sym_name = _symbol_name_for(con, r["security_id"], as_of)
        sp = split.get(sid, {})
        rows.append(
            {
                "security_id": sid,
                "symbol": sym or sid,
                "name": r.get("name") or sym_name or "",
                "mentions": int(r["mentions"]) if r["mentions"] is not None else 0,
                "upvotes": int(r["upvotes"]) if r.get("upvotes") is not None else None,
                "rank": r.get("rank"),
                "cohort": r.get("cohort"),
                "mention_delta_pct": r.get("mention_delta_pct"),
                "upvote_ratio": r.get("upvote_ratio"),
                "upvote_delta_pct": r.get("upvote_delta_pct"),
                "positive_ratio": sp.get("positive_ratio", r.get("positive_ratio")),
                "neutral_ratio": sp.get("neutral_ratio"),
                "negative_ratio": sp.get("negative_ratio"),
                "mean_score": r.get("mean_score"),
                "total_messages": sp.get("total_messages") or r.get("total_messages"),
                "trend": trends.get(sid, []),
            }
        )
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
    if df.is_empty():
        return JSONResponse([])
    df = df.sort("effective_date", descending=True)
    return JSONResponse(_pl_to_dicts(df))


# ── Insider transactions ──────────────────────────────────────────────────


@router.get("/insider/{symbol}", response_model=list[TransactionRow])
async def insider_tx(symbol: str, as_of: datetime | None = None, limit: int = 50):
    _check_enabled()
    if as_of is None:
        as_of = _now()
    con = _get_con()
    sec_id = resolve_security(con, symbol, as_of=as_of.date())
    if sec_id is None:
        sec_id = symbol
    df = pit_read(con, table="insider_tx", security_ids=[sec_id], as_of=as_of)
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
    try:
        df = pit_read(con, table="analyst_estimates", security_ids=[sec_id], as_of=as_of)
    except Exception:
        return JSONResponse([])
    if df.is_empty():
        return JSONResponse([])
    df = df.sort("effective_date", descending=True).head(min(limit, 500))
    return JSONResponse(_pl_to_dicts(df))


# ── Indicators glossary ──────────────────────────────────────────────────


@router.get("/indicators/glossary")
async def indicator_glossary():
    """Return the full indicator glossary, optionally filtered by category.

    Query param ``?category=Trend`` to filter to one category.
    """
    _check_enabled()
    return _GLOSSARY
