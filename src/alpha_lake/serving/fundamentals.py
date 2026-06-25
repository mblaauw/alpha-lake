from __future__ import annotations

from datetime import datetime
from typing import Any

import duckdb
import polars as pl

from alpha_lake.interop import duckdb_to_polars
from alpha_lake.interpretation.fundamentals_glossary import (
    get_metric_threshold_profile_id,
    get_threshold_profile,
    resolve_fundamental_state,
)

_VALID_PRICE_MODES = frozenset({"raw", "split_adjusted"})
_PRICE_CURRENCY = "USD"

_VALUATION_INPUTS: dict[str, tuple[str, str]] = {
    "fundamentals.valuation.price_to_earnings_ttm": (
        "fundamentals.profitability.diluted_eps_ttm",
        "price / diluted_eps_ttm",
    ),
    "fundamentals.valuation.price_to_sales_ttm": (
        "fundamentals.scale.revenue_per_share_ttm",
        "price / revenue_per_share_ttm",
    ),
    "fundamentals.valuation.price_to_fcf_ttm": (
        "fundamentals.cash_flow_quality.fcf_per_share_ttm",
        "price / free_cash_flow_per_share_ttm",
    ),
}


def read_fundamental_metrics_asof(
    con: duckdb.DuckDBPyConnection,
    security_ids: list[str],
    as_of: datetime | None,
    categories: list[str] | None = None,
    metric_ids: list[str] | None = None,
    price_mode: str = "raw",
    snapshot_id: str | None = None,
) -> pl.DataFrame:
    if as_of is None:
        raise ValueError("as_of is required for fundamental metric research reads")
    if price_mode not in _VALID_PRICE_MODES:
        raise ValueError(f"Unknown price_mode '{price_mode}'. Valid: {sorted(_VALID_PRICE_MODES)}")

    _pin_snapshot(con, snapshot_id)
    _ensure_kernel(con)

    requested_metric_ids = set(metric_ids or [])
    query_categories, query_metric_ids = _query_filters(categories, metric_ids)
    raw = duckdb_to_polars(
        con,
        "SELECT * FROM fundamental_metrics_asof(?, ?, ?, ?)",
        [security_ids, as_of, query_categories, query_metric_ids],
    )

    price_context = _read_price_context(con, security_ids, as_of, price_mode, snapshot_id)
    visible_raw = _visible_rows(raw, categories, metric_ids)
    rows = [
        _enrich_metric(row, price_context.get(row["security_id"]), price_mode)
        for row in visible_raw
    ]
    rows.extend(
        _valuation_rows(raw, price_context, price_mode, requested_metric_ids, categories, as_of)
    )
    if not rows:
        return _empty_output()
    return pl.DataFrame(rows).with_columns(
        pl.col("value").cast(pl.Float64),
        pl.col("price_close").cast(pl.Float64),
        pl.col("period_end").cast(pl.Date),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("price_effective_date").cast(pl.Date),
        pl.col("price_available_at").cast(pl.Datetime(time_zone="UTC")),
    )


def _query_filters(
    categories: list[str] | None, metric_ids: list[str] | None
) -> tuple[list[str] | None, list[str] | None]:
    ids = set(metric_ids or [])
    wants_valuation = (
        categories is None
        or "valuation" in categories
        or any(mid in _VALUATION_INPUTS for mid in ids)
    )
    if categories is None and metric_ids is None:
        return None, None
    if wants_valuation:
        ids.update(denominator for denominator, _ in _VALUATION_INPUTS.values())
        return None, sorted(ids)
    return categories, sorted(ids) if ids else None


def _visible_rows(
    metrics: pl.DataFrame, categories: list[str] | None, metric_ids: list[str] | None
) -> list[dict[str, Any]]:
    rows = metrics.rows(named=True)
    if categories is not None:
        rows = [r for r in rows if r["category"] in categories]
    if metric_ids is not None:
        requested = set(metric_ids)
        rows = [r for r in rows if r["metric_id"] in requested]
    return rows


def _valuation_rows(
    metrics: pl.DataFrame,
    price_context: dict[str, dict[str, Any]],
    price_mode: str,
    requested_metric_ids: set[str],
    categories: list[str] | None,
    as_of: datetime,
) -> list[dict[str, Any]]:
    if categories is not None and "valuation" not in categories:
        return []
    rows: list[dict[str, Any]] = []
    by_security_metric = {(r["security_id"], r["metric_id"]): r for r in metrics.rows(named=True)}
    for valuation_id, (input_id, basis) in _VALUATION_INPUTS.items():
        if requested_metric_ids and valuation_id not in requested_metric_ids:
            continue
        for security_id in sorted({str(r["security_id"]) for r in metrics.rows(named=True)}):
            input_row = by_security_metric.get((security_id, input_id))
            if input_row is None:
                continue
            price = price_context.get(security_id)
            rows.append(_valuation_row(valuation_id, input_row, price, price_mode, basis, as_of))
    return rows


def _valuation_row(
    metric_id: str,
    input_row: dict[str, Any],
    price: dict[str, Any] | None,
    price_mode: str,
    basis: str,
    as_of: datetime,
) -> dict[str, Any]:
    row = dict(input_row)
    row["metric_id"] = metric_id
    row["category"] = "valuation"
    row["unit"] = "multiple"
    row["currency"] = None
    row["calculation_basis"] = basis
    row["available_at"] = max(input_row["available_at"], price["available_at"]) if price else as_of

    value = None
    quality_status = "valid"
    unavailable_reason = ""
    if price is None:
        quality_status = "unavailable"
        unavailable_reason = "price_unavailable_as_of"
    elif input_row.get("currency") not in (None, _PRICE_CURRENCY):
        quality_status = "unavailable"
        unavailable_reason = "currency_mismatch_without_pit_fx"
    elif input_row.get("value") is None or float(input_row["value"]) <= 0:
        quality_status = "not_meaningful"
        unavailable_reason = "non_positive_denominator"
    else:
        value = float(price["close"]) / float(input_row["value"])
    row["value"] = value
    row["quality_status"] = quality_status
    return _enrich_metric(row, price, price_mode, unavailable_reason=unavailable_reason)


def _read_price_context(
    con: duckdb.DuckDBPyConnection,
    security_ids: list[str],
    as_of: datetime,
    price_mode: str,
    snapshot_id: str | None,
) -> dict[str, dict[str, Any]]:
    from alpha_lake.serving import read_bars_adjusted

    bars = read_bars_adjusted(
        con,
        security_ids,
        as_of,
        price_mode=price_mode,
        snapshot_id=snapshot_id,
    )
    if bars.is_empty():
        return {}
    latest = (
        bars.sort(["security_id", "effective_date", "available_at"])
        .group_by("security_id", maintain_order=True)
        .last()
    )
    return {str(row["security_id"]): row for row in latest.rows(named=True)}


def _enrich_metric(
    row: dict[str, Any],
    price: dict[str, Any] | None,
    price_mode: str,
    *,
    unavailable_reason: str = "",
) -> dict[str, Any]:
    state = _state_for(row)
    profile_id = get_metric_threshold_profile_id(row["metric_id"])
    profile = get_threshold_profile(profile_id) if profile_id else None
    if state != "available" or row.get("value") is None:
        threshold_state, tone, label = state, "gray", state.replace("_", " ")
    elif profile is not None:
        threshold_state, tone, label = resolve_fundamental_state(profile, row["value"])
    else:
        threshold_state, tone, label = "available", "gray", "available"
    return {
        **row,
        "state": state,
        "threshold_profile_id": profile_id,
        "threshold_state": threshold_state,
        "tone": tone,
        "label": label,
        "display_value": _display_value(row.get("value"), row.get("unit")),
        "display_decimals": _display_decimals(row.get("unit")),
        "display_suffix": _display_suffix(row.get("unit")),
        "unavailable_reason": unavailable_reason,
        "price_mode": price_mode,
        "price_currency": _PRICE_CURRENCY,
        "price_close": price.get("close") if price else None,
        "price_effective_date": price.get("effective_date") if price else None,
        "price_available_at": price.get("available_at") if price else None,
    }


def _state_for(row: dict[str, Any]) -> str:
    quality = row.get("quality_status") or "valid"
    if quality in {"unavailable", "not_meaningful", "not_applicable", "stale", "degraded"}:
        return str(quality)
    if row.get("value") is None:
        return "unavailable"
    return "available"


def _display_value(value: Any, unit: Any) -> str:
    if value is None:
        return "Unavailable"
    numeric = float(value)
    if unit == "percent":
        return f"{numeric:.2f}%"
    if unit == "multiple":
        return f"{numeric:.2f}x"
    if unit == "currency":
        return f"{numeric:.2f}"
    return f"{numeric:.2f}"


def _display_decimals(unit: Any) -> int:
    return 2 if unit in {"percent", "multiple", "currency"} else 2


def _display_suffix(unit: Any) -> str:
    if unit == "percent":
        return "%"
    if unit == "multiple":
        return "x"
    return ""


def _pin_snapshot(con: duckdb.DuckDBPyConnection, snapshot_id: str | None) -> None:
    if snapshot_id is not None:
        from alpha_lake.catalog import set_snapshot

        set_snapshot(con, snapshot_id)


def _ensure_kernel(con: duckdb.DuckDBPyConnection) -> None:
    from alpha_lake.kernel import register_kernel

    register_kernel(con)


def _empty_output() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "security_id": pl.String,
            "metric_id": pl.String,
            "metric_version": pl.String,
            "category": pl.String,
            "period_kind": pl.String,
            "period_end": pl.Date,
            "available_at": pl.Datetime(time_zone="UTC"),
            "value": pl.Float64,
            "unit": pl.String,
            "currency": pl.String,
            "source_currency": pl.String,
            "source_period_ends": pl.String,
            "source_version_hashes": pl.String,
            "calculation_basis": pl.String,
            "quality_status": pl.String,
            "calculation_version": pl.String,
            "ingestion_run_id": pl.String,
            "source_id": pl.String,
            "source_fetch_id": pl.String,
            "raw_payload_hash": pl.String,
            "content_hash": pl.String,
            "version_hash": pl.String,
            "schema_version": pl.Int64,
            "parser_version": pl.Int64,
            "normalization_version": pl.Int64,
            "state": pl.String,
            "threshold_profile_id": pl.String,
            "threshold_state": pl.String,
            "tone": pl.String,
            "label": pl.String,
            "display_value": pl.String,
            "display_decimals": pl.Int64,
            "display_suffix": pl.String,
            "unavailable_reason": pl.String,
            "price_mode": pl.String,
            "price_currency": pl.String,
            "price_close": pl.Float64,
            "price_effective_date": pl.Date,
            "price_available_at": pl.Datetime(time_zone="UTC"),
        }
    )


__all__ = ["read_fundamental_metrics_asof"]
