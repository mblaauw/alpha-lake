from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import polars as pl  # type: ignore[unresolved-import]

from alpha_lake.calendar_ import shift_trading_days
from alpha_lake.derived import atr, bollinger_bands, ema, macd, rsi, sma

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
