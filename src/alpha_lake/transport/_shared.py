"""Shared utilities for the Alpha-Lake REST API transport layer."""

from __future__ import annotations

import json
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


def _parse_indicators(spec: str) -> list[tuple[str, list[int | float]]]:
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
    return _pl_to_dicts(df)


def _dataset_health(
    con: duckdb.DuckDBPyConnection,
    tables: list[str],
    *,
    snapshot_id: str | None = None,
) -> dict[str, dict[str, object]]:
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
    result: dict[str, dict[str, object]] = {"datasets": datasets}
    if snapshot_id:
        result["snapshot_id"] = snapshot_id
    return result


def _compute_and_serialize_indicators(
    con: duckdb.DuckDBPyConnection,
    sec_id: str,
    parsed: list[tuple[str, list[int | float]]],
    as_of: datetime,
    *,
    start: date | None = None,
    end: date | None = None,
) -> dict[str, list[Any]]:
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
