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
