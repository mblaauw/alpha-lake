from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import duckdb  # type: ignore[unresolved-import]
import polars as pl  # type: ignore[unresolved-import]

from alpha_lake.calendar_ import shift_trading_days
from alpha_lake.derived import atr, bollinger_bands, ema, macd, rsi, sma
from alpha_lake.serving import read_bars_adjusted, read_bars_asof

_INDICATOR_MAP: dict[str, Any] = {
    "sma": sma,
    "ema": ema,
    "rsi": rsi,
    "bollinger": bollinger_bands,
    "atr": atr,
    "macd": macd,
}

_DEFAULT_ARGS: dict[str, list[int | float]] = {
    "sma": [20],
    "ema": [12],
    "rsi": [14],
    "bollinger": [20, 2],
    "atr": [14],
    "macd": [12, 26, 9],
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
_VALID_PRICE_MODES = frozenset({"raw", "split_adjusted"})


def _validate_price_mode(price_mode: str) -> None:
    """Raise ``HTTPException(422)`` on invalid ``price_mode`` values."""
    if price_mode not in _VALID_PRICE_MODES:
        from fastapi import HTTPException

        raise HTTPException(
            422,
            f"Unknown price_mode '{price_mode}'. Valid: {sorted(_VALID_PRICE_MODES)}",
        )


def _serialize_bars_df(df: pl.DataFrame) -> dict[str, list[Any]]:
    """Convert a bars DataFrame (row-oriented) to a JSON-safe column-oriented dict.

    Handles datetime -> isoformat, float from numeric, str from string columns.
    """
    result: dict[str, list[Any]] = {}
    for col in df.columns:
        if col in ("effective_date",):
            result[col] = [d.isoformat() if d is not None else None for d in df[col]]
        elif col in ("available_at",):
            result[col] = [str(v) if v is not None else None for v in df[col]]
        elif df[col].dtype in (pl.Float64, pl.Float32, pl.Int64, pl.Int32):
            result[col] = [float(v) if v is not None else None for v in df[col]]
        elif df[col].dtype in (pl.Utf8, pl.String):
            result[col] = [str(v) if v is not None else None for v in df[col]]
        else:
            result[col] = [str(v) if v is not None else None for v in df[col]]
    return result


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_indicators(spec: str) -> list[tuple[str, list[int | float]]]:
    """Parse indicator spec like ``sma:20;ema:12;bollinger:20,2;macd:12,26,9``.

    Supports two separator styles:
    - ``;`` separates indicators, ``:`` separates name from comma-delimited args.
    - Legacy: ``sma,ema,rsi`` (bare names, no args — separated by ``,``, only
      used when no ``:`` or ``;`` is present).

    Args that represent whole numbers are returned as ``int`` so they pass
    cleanly to window-size parameters.
    """
    sep = ";" if ";" in spec or ":" in spec else ","
    result: list[tuple[str, list[int | float]]] = []
    for part in spec.split(sep):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            name, args_str = part.split(":", 1)
            args: list[int | float] = []
            for a in args_str.split(","):
                v = float(a.strip())
                args.append(int(v) if v == int(v) else v)
            result.append((name.strip(), args))
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


def _fetch_bars(
    con: duckdb.DuckDBPyConnection,
    sec_id: str,
    as_of: datetime,
    *,
    start: date | None = None,
    end: date | None = None,
    snapshot_id: str | None = None,
    price_mode: str = "raw",
) -> list[dict[str, Any]]:
    """Fetch bars for a pre-validated security.

    All inputs (sec_id, as_of, price_mode, lookback) must be validated
    by the caller. This function only builds kwargs and queries.
    """
    kwargs: dict[str, Any] = {"security_ids": [sec_id], "as_of": as_of}
    if start:
        kwargs["start_date"] = start
    if end:
        kwargs["end_date"] = end
    if snapshot_id:
        kwargs["snapshot_id"] = snapshot_id
    if price_mode != "raw":
        kwargs["price_mode"] = price_mode
    df = read_bars_adjusted(con, **kwargs) if price_mode != "raw" else read_bars_asof(con, **kwargs)
    return _pl_to_dicts(df)


def _compute_and_serialize_indicators(
    con: duckdb.DuckDBPyConnection,
    sec_id: str,
    parsed: list[tuple[str, list[int | float]]],
    as_of: datetime,
    *,
    start: date | None = None,
    end: date | None = None,
) -> dict[str, list[Any]]:
    """Compute requested indicators and return a column-oriented dict.

    ``parsed`` must be pre-validated (all names in ``_INDICATOR_MAP``).
    The warmup window is computed automatically to ensure stable indicator
    values at the requested ``start`` date.
    """
    parsed = [(n, list(a) if a else list(_DEFAULT_ARGS.get(n, []))) for n, a in parsed]
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

    bars_df = read_bars_asof(con, **kwargs)
    if bars_df.height == 0:
        return {}

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

    return result
