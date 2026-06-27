"""Shared utilities for the Alpha-Lake REST API transport layer."""

from __future__ import annotations

import json
import time
from datetime import UTC, date, datetime
from typing import Any

import duckdb  # type: ignore[unresolved-import]
import polars as pl  # type: ignore[unresolved-import]

from alpha_lake.calendar_ import shift_trading_days
from alpha_lake.derived import atr, bollinger_bands, ema, macd, rsi, sma
from alpha_lake.serving import pit_read, read_bars_adjusted, read_bars_asof

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
_CACHE_TTL = 30  # seconds


class _TTLCache:
    """Simple in-memory TTL cache with a max size."""

    def __init__(self, ttl: float = _CACHE_TTL, maxsize: int = 256) -> None:
        self._ttl = ttl
        self._maxsize = maxsize
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires, value = entry
        if time.monotonic() > expires:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        if len(self._store) >= self._maxsize:
            oldest = min(self._store.keys(), key=lambda k: self._store[k][0])
            del self._store[oldest]
        self._store[key] = (time.monotonic() + self._ttl, value)

    def clear(self) -> None:
        self._store.clear()


_RESPONSE_CACHE = _TTLCache()

_AUDIT_COLUMNS: frozenset[str] = frozenset(
    {
        "source_fetch_id",
        "raw_payload_hash",
        "ingestion_run_id",
        "content_hash",
        "version_hash",
        "schema_version",
        "parser_version",
        "normalization_version",
        "source_id",
        "quality_status",
    }
)


def _validate_price_mode(price_mode: str) -> None:
    if price_mode not in _VALID_PRICE_MODES:
        from fastapi import HTTPException

        raise HTTPException(
            422,
            f"Unknown price_mode '{price_mode}'. Valid: {sorted(_VALID_PRICE_MODES)}",
        )


def _serialize_bars_df(df: pl.DataFrame) -> dict[str, list[Any]]:
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


def _parse_date_list(raw: str) -> list[str] | None:
    try:
        dates = json.loads(raw)
        if isinstance(dates, list):
            return [d for d in dates if d]
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(dt: datetime) -> datetime:
    """Normalize a datetime to tz-aware UTC for TIMESTAMPTZ comparisons."""
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _parse_args(args_str: str) -> list[int | float]:
    """Parse comma-separated arg string into list of int or float."""
    result: list[int | float] = []
    for a in args_str.split(","):
        a = a.strip()
        if not a:
            continue
        v = float(a)
        result.append(int(v) if v == int(v) else v)
    return result


def _parse_indicators(spec: str) -> list[tuple[str, list[int | float]]]:
    """Parse indicator spec string into list of (name, args) tuples.

    Two formats:
      - semicolon-separated:  "sma:20,50;ema:12,26;rsi:14"
      - comma-separated:      "sma:20,50,200,ema:12,26,rsi:14"
    """
    parts = spec.split(";") if ";" in spec else spec.split(",")
    result: list[tuple[str, list[int | float]]] = []
    current_name: str | None = None
    current_args: list[int | float] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            if current_name is not None:
                result.append((current_name, current_args))
            name, args_str = part.split(":", 1)
            current_name = name.strip()
            current_args = _parse_args(args_str)
        elif current_name is not None:
            current_args.append(float(part))
        else:
            result.append((part, []))
    if current_name is not None:
        result.append((current_name, current_args))
    return result


def _compute_warmup(
    indicator: str, args: list[int | float], start: date | None, exchange: str = "XNYS"
) -> date | None:
    if start is None:
        return None
    mult = _RECURSIVE_MULTIPLIER.get(indicator, 1)
    window = int(args[0]) if args else 14
    return shift_trading_days(start, -(window * mult), exchange=exchange)


def _fundamental_row_to_item(
    row: dict[str, Any],
    include_set: set[str],
    *,
    _get_glossary_entry=None,
    _get_threshold_profile=None,
) -> dict[str, Any]:
    if _get_glossary_entry is None:
        from alpha_lake.interpretation.fundamentals_glossary import get_glossary_entry

        _get_glossary_entry = get_glossary_entry
    if _get_threshold_profile is None:
        from alpha_lake.interpretation.fundamentals_glossary import get_threshold_profile

        _get_threshold_profile = get_threshold_profile

    entry = _get_glossary_entry(row["metric_id"])
    item: dict[str, Any] = {
        "metric_id": row["metric_id"],
        "name": entry.name if entry else row["metric_id"],
        "category": row["category"],
        "period_kind": row.get("period_kind", ""),
        "period_end": row["period_end"].isoformat() if row.get("period_end") else None,
        "available_at": row["available_at"].isoformat() if row.get("available_at") else None,
        "value": row.get("value"),
        "unit": row.get("unit", ""),
        "state": row.get("state", ""),
        "threshold_profile_id": row.get("threshold_profile_id", ""),
        "threshold_state": row.get("threshold_state", ""),
        "tone": row.get("tone", ""),
        "label": row.get("label", ""),
        "display_value": row.get("display_value"),
        "display_decimals": row.get("display_decimals", 2),
        "display_suffix": row.get("display_suffix", ""),
        "quality_status": row.get("quality_status", ""),
        "unavailable_reason": row.get("unavailable_reason", ""),
        "price_close": row.get("price_close"),
        "price_effective_date": row["price_effective_date"].isoformat()
        if row.get("price_effective_date")
        else None,
        "price_available_at": row["price_available_at"].isoformat()
        if row.get("price_available_at")
        else None,
        "price_mode": row.get("price_mode", "raw"),
    }
    if "inputs" in include_set and entry:
        item["inputs"] = list(entry.inputs)
        item["basis"] = entry.basis
        item["calculation_basis"] = row.get("calculation_basis") or entry.formula
        item["source_period_ends"] = (
            _parse_date_list(row["source_period_ends"]) if row.get("source_period_ends") else None
        )
    if "definitions" in include_set and entry:
        item["description"] = entry.description
        item["what_it_answers"] = entry.what_it_answers
        item["formula"] = entry.formula
        item["metric_version"] = row.get("metric_version")
        profile = _get_threshold_profile(entry.threshold_profile_id)
        if profile:
            item["threshold_profile"] = {
                "profile_id": profile.profile_id,
                "version": profile.version,
                "method": profile.method,
                "description": profile.description,
                "min_peer_count": profile.min_peer_count,
                "bands": [
                    {
                        "state": b.state,
                        "tone": b.tone,
                        "label": b.label,
                        "min_value": b.min_value,
                        "max_value": b.max_value,
                    }
                    for b in profile.bands
                ],
            }
    if "provenance" in include_set:
        for col in (
            "source_id",
            "version_hash",
            "content_hash",
            "schema_version",
            "parser_version",
            "normalization_version",
            "source_fetch_id",
            "ingestion_run_id",
        ):
            if col in row:
                item[col] = row[col]
    return item


def _pl_to_dicts(df: pl.DataFrame) -> list[dict[str, Any]]:
    return [{k: _v(v) for k, v in row.items()} for row in df.rows(named=True)]


def _v(val: Any) -> Any:
    if isinstance(val, datetime | date):
        return val.isoformat()
    return val


def _parse_fields(fields_str: str | None) -> set[str] | None:
    """Parse comma-separated field selection into a set of column names.

    Returns ``None`` when no selection is given (return all columns).
    """
    if not fields_str:
        return None
    parsed = {s.strip() for s in fields_str.split(",") if s.strip()}
    return parsed if parsed else None


def _strip_audit_cols(
    items: list[dict[str, Any]], include_set: set[str] | None
) -> list[dict[str, Any]]:
    """Remove audit/provenance columns from row dicts unless ``provenance`` is requested."""
    if include_set and "provenance" in include_set:
        return items
    return [{k: v for k, v in row.items() if k not in _AUDIT_COLUMNS} for row in items]


def _strip_audit_cols_dict(
    result: dict[str, list[Any]], include_set: set[str] | None
) -> dict[str, list[Any]]:
    """Remove audit/provenance column keys from a column-oriented dict."""
    if include_set and "provenance" in include_set:
        return result
    return {k: v for k, v in result.items() if k not in _AUDIT_COLUMNS}


def _fetch_bars(
    con: duckdb.DuckDBPyConnection,
    sec_id: str,
    as_of: datetime,
    *,
    start: date | None = None,
    end: date | None = None,
    snapshot_id: str | None = None,
    price_mode: str = "raw",
    include_set: set[str] | None = None,
    fields: set[str] | None = None,
) -> list[dict[str, Any]]:
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
    if fields is not None and not df.is_empty():
        available = [c for c in fields if c in df.columns]
        if available:
            df = df.select(available)
    return _strip_audit_cols(_pl_to_dicts(df), include_set)


def _fetch_dataset(
    con: duckdb.DuckDBPyConnection,
    table: str,
    sec_id: str,
    as_of: datetime,
    *,
    start: date | None = None,
    end: date | None = None,
    snapshot_id: str | None = None,
    source_precedence_dataset: str | None = None,
    include_set: set[str] | None = None,
    fields: set[str] | None = None,
) -> list[dict[str, Any]]:
    kwargs: dict[str, Any] = {
        "table": table,
        "security_ids": [sec_id],
        "as_of": as_of,
    }
    if start:
        kwargs["start_date"] = start
    if end:
        kwargs["end_date"] = end
    if snapshot_id:
        kwargs["snapshot_id"] = snapshot_id
    if source_precedence_dataset:
        kwargs["source_precedence_dataset"] = source_precedence_dataset
    df = pit_read(con, **kwargs)
    if fields is not None and not df.is_empty():
        available = [c for c in fields if c in df.columns]
        if available:
            df = df.select(available)
    return _strip_audit_cols(_pl_to_dicts(df), include_set)


def _fetch_multi(
    con: duckdb.DuckDBPyConnection,
    table: str,
    sec_ids: list[str],
    as_of: datetime,
    *,
    start: date | None = None,
    end: date | None = None,
    snapshot_id: str | None = None,
    source_precedence_dataset: str | None = None,
    include_set: set[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Batch-fetch a dataset for multiple security_ids, grouped by sec_id."""
    kwargs: dict[str, Any] = {
        "table": table,
        "security_ids": sec_ids,
        "as_of": as_of,
    }
    if start:
        kwargs["start_date"] = start
    if end:
        kwargs["end_date"] = end
    if snapshot_id:
        kwargs["snapshot_id"] = snapshot_id
    if source_precedence_dataset:
        kwargs["source_precedence_dataset"] = source_precedence_dataset
    df = pit_read(con, **kwargs)
    items = _strip_audit_cols(_pl_to_dicts(df), include_set)
    result: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        sid = item.get("security_id", "")
        result.setdefault(sid, []).append(item)
    return result


def _parse_as_of(as_of: datetime | None) -> datetime:
    """Default as_of to now() when not provided."""
    return as_of if as_of is not None else datetime.now(UTC)


def _resolve_or_raise(con: duckdb.DuckDBPyConnection, symbol: str, as_of: date) -> str:
    """Resolve symbol to security_id, raising 404 on failure."""
    from alpha_lake.security_master import resolve as _resolve

    sec_id = _resolve(con, symbol, as_of=as_of)
    if sec_id is None:
        from fastapi import HTTPException

        raise HTTPException(404, f"Unknown symbol: {symbol}")
    return sec_id


def _handle_bars(
    con: duckdb.DuckDBPyConnection,
    sec_id: str,
    as_of: datetime,
    *,
    start: date | None = None,
    end: date | None = None,
    snapshot_id: str | None = None,
    price_mode: str = "raw",
    include_set: set[str] | None = None,
    fields: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Shared bars fetch logic for both app and dashboard routers."""
    result = _fetch_bars(
        con,
        sec_id,
        as_of,
        start=start,
        end=end,
        snapshot_id=snapshot_id,
        price_mode=price_mode,
        include_set=include_set,
        fields=fields,
    )
    if not result:
        from fastapi import HTTPException

        raise HTTPException(404, "Unknown symbol or no bars available")
    return result


def _handle_bars_indicators(
    con: duckdb.DuckDBPyConnection,
    sec_id: str,
    parsed: list[tuple[str, list[int | float]]],
    as_of: datetime,
    *,
    start: date | None = None,
    end: date | None = None,
    include_set: set[str] | None = None,
    fields: set[str] | None = None,
) -> dict[str, list[Any]]:
    """Shared bars/indicators fetch + compute logic."""
    result = _compute_and_serialize_indicators(
        con,
        sec_id,
        parsed,
        as_of,
        start=start,
        end=end,
        include_set=include_set,
        fields=fields,
    )
    if not result:
        from fastapi import HTTPException

        raise HTTPException(404, "Unknown symbol or no bars available")
    return result


def _dataset_health(
    con: duckdb.DuckDBPyConnection,
    tables: list[str],
    *,
    snapshot_id: str | None = None,
) -> dict[str, object]:
    datasets: dict[str, dict[str, object]] = {}
    for table in tables:
        try:
            row = con.execute(
                "SELECT COUNT(*) AS cnt, MAX(effective_date) AS latest,"
                " MAX(available_at) AS newest "
                f"FROM {table}"
            ).fetchone()
            count = row[0] if row else 0
            latest_eff = str(row[1]) if row and row[1] else None
            latest_avail = str(row[2]) if row and row[2] else None
            datasets[table] = {
                "status": "ok" if count > 0 else "empty",
                "row_count": count,
                "latest_effective_date": latest_eff,
                "latest_available_at": latest_avail,
            }
        except Exception as exc:
            datasets[table] = {"status": "error", "detail": str(exc)}
    result: dict[str, object] = {"datasets": datasets}
    if snapshot_id:
        result["snapshot_id"] = snapshot_id
    return result


def _compute_indicators_from_df(
    bars_df: pl.DataFrame,
    parsed: list[tuple[str, list[int | float]]],
    *,
    start: date | None = None,
    include_set: set[str] | None = None,
    fields: set[str] | None = None,
) -> dict[str, list[Any]]:
    """Compute indicators from a pre-fetched bars DataFrame (one security)."""
    if bars_df.height == 0:
        return {}

    bars_df = bars_df.sort("effective_date")

    if fields is not None:
        bar_fields = {c for c in bars_df.columns if c in fields}
        if bar_fields:
            bars_df = bars_df.select(list(bar_fields))

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

    if start and bars_df["effective_date"].min() is not None and start is not None:
        mask = [str(d) >= start.isoformat() for d in bars_df["effective_date"].to_list()]
        for key in list(result.keys()):
            result[key] = [v for v, m in zip(result[key], mask, strict=True) if m]

    result = _strip_audit_cols_dict(result, include_set)

    if fields is not None:
        result = {k: v for k, v in result.items() if k in fields}

    return result


def _cache_key(prefix: str, sec_id: str, as_of: datetime, **kwargs: Any) -> str:
    parts = [prefix, sec_id, as_of.isoformat()]
    for k, v in sorted(kwargs.items()):
        if v is not None and v != set():
            parts.append(f"{k}={v!r}")
    return ":".join(parts)


def _compute_and_serialize_indicators(
    con: duckdb.DuckDBPyConnection,
    sec_id: str,
    parsed: list[tuple[str, list[int | float]]],
    as_of: datetime,
    *,
    start: date | None = None,
    end: date | None = None,
    include_set: set[str] | None = None,
    fields: set[str] | None = None,
) -> dict[str, list[Any]]:
    parsed = [(n, list(a) if a else list(_DEFAULT_ARGS.get(n, []))) for n, a in parsed]

    ck = _cache_key(
        "indicators",
        sec_id,
        as_of,
        start=start,
        end=end,
        parsed=parsed,
        include=include_set,
        fields=fields,
    )
    cached = _RESPONSE_CACHE.get(ck)
    if cached is not None:
        return cached
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

    # Pre-filter DataFrame columns when fields are requested
    if fields is not None:
        bar_fields = {c for c in bars_df.columns if c in fields}
        if bar_fields:
            bars_df = bars_df.select(list(bar_fields))

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

    result = _strip_audit_cols_dict(result, include_set)

    if fields is not None:
        result = {k: v for k, v in result.items() if k in fields}

    _RESPONSE_CACHE.set(ck, result)
    return result
