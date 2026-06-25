from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

import polars as pl

from alpha_lake.canonical import compute_version_hash
from alpha_lake.models.fundamental_metric_fact import FundamentalMetricFact

CALCULATION_VERSION = "1.0.0"
METRIC_VERSION = "1.0.0"


def compute_fundamental_period_metrics(
    facts: pl.DataFrame,
    as_of: datetime,
    *,
    ingestion_run_id: str = "",
    calculation_version: str = CALCULATION_VERSION,
) -> pl.DataFrame:
    """Compute long-form fundamental metrics from canonical financial facts.

    Input facts must already be canonical `FundamentalFact`-shaped rows. This
    function enforces the PIT boundary with `available_at <= as_of`, resolves
    restated rows by newest eligible knowledge, builds standalone quarter TTM
    inputs, and uses latest instant facts for MRQ-style balance-sheet metrics.
    """
    if facts.is_empty():
        return _empty_output()

    facts = facts.filter(pl.col("available_at") <= as_of)
    if facts.is_empty():
        return _empty_output()

    selected = _latest_facts(facts)
    rows: list[dict[str, Any]] = []

    for sid in sorted({str(r["security_id"]) for r in selected}):
        sf = [r for r in selected if r["security_id"] == sid]
        quarters = _standalone_quarter_flows(sf)
        ttm = {item: _latest_ttm(quarters, item) for item in _FLOW_ITEMS}
        prior_ttm = {item: _prior_ttm(quarters, item) for item in _GROWTH_ITEMS}
        instants = {item: _latest_instant(sf, item) for item in _INSTANT_ITEMS}

        _add_ttm_value(
            rows,
            sid,
            "fundamentals.scale.revenue_ttm",
            "scale",
            ttm["revenue"],
            ingestion_run_id,
            calculation_version,
        )
        _add_ttm_value(
            rows,
            sid,
            "fundamentals.scale.ebitda_ttm",
            "scale",
            ttm["ebitda"],
            ingestion_run_id,
            calculation_version,
        )
        _add_ratio(
            rows,
            sid,
            "fundamentals.profitability.gross_margin_ttm",
            "profitability",
            ttm["gross_profit"],
            ttm["revenue"],
            "percent",
            "gross_profit_ttm / revenue_ttm * 100",
            ingestion_run_id,
            calculation_version,
            scale=100.0,
        )
        _add_ratio(
            rows,
            sid,
            "fundamentals.profitability.operating_margin_ttm",
            "profitability",
            ttm["operating_income"],
            ttm["revenue"],
            "percent",
            "operating_income_ttm / revenue_ttm * 100",
            ingestion_run_id,
            calculation_version,
            scale=100.0,
        )
        _add_ratio(
            rows,
            sid,
            "fundamentals.profitability.ebitda_margin_ttm",
            "profitability",
            ttm["ebitda"],
            ttm["revenue"],
            "percent",
            "ebitda_ttm / revenue_ttm * 100",
            ingestion_run_id,
            calculation_version,
            scale=100.0,
        )
        _add_ratio(
            rows,
            sid,
            "fundamentals.profitability.net_margin_ttm",
            "profitability",
            ttm["net_income"],
            ttm["revenue"],
            "percent",
            "net_income_ttm / revenue_ttm * 100",
            ingestion_run_id,
            calculation_version,
            scale=100.0,
        )

        fcf = _free_cash_flow(ttm["operating_cash_flow"], ttm["capital_expenditure"])
        _add_ratio(
            rows,
            sid,
            "fundamentals.cash_flow_quality.cfo_to_net_income_ttm",
            "cash_flow_quality",
            ttm["operating_cash_flow"],
            ttm["net_income"],
            "multiple",
            "operating_cash_flow_ttm / net_income_ttm",
            ingestion_run_id,
            calculation_version,
        )
        _add_ratio(
            rows,
            sid,
            "fundamentals.cash_flow_quality.fcf_conversion_ttm",
            "cash_flow_quality",
            fcf,
            ttm["net_income"],
            "multiple",
            "free_cash_flow_ttm / net_income_ttm",
            ingestion_run_id,
            calculation_version,
        )
        _add_ratio(
            rows,
            sid,
            "fundamentals.profitability.fcf_margin_ttm",
            "profitability",
            fcf,
            ttm["revenue"],
            "percent",
            "free_cash_flow_ttm / revenue_ttm * 100",
            ingestion_run_id,
            calculation_version,
            scale=100.0,
        )

        _add_growth(
            rows,
            sid,
            "fundamentals.growth.revenue_yoy_ttm",
            "growth",
            ttm["revenue"],
            prior_ttm["revenue"],
            "revenue_ttm / revenue_ttm_1y_ago - 1",
            ingestion_run_id,
            calculation_version,
        )
        _add_growth(
            rows,
            sid,
            "fundamentals.growth.eps_diluted_yoy_ttm",
            "growth",
            ttm["diluted_eps"],
            prior_ttm["diluted_eps"],
            "eps_ttm / eps_ttm_1y_ago - 1",
            ingestion_run_id,
            calculation_version,
        )
        _add_growth(
            rows,
            sid,
            "fundamentals.growth.ebitda_yoy_ttm",
            "growth",
            ttm["ebitda"],
            prior_ttm["ebitda"],
            "ebitda_ttm / ebitda_ttm_1y_ago - 1",
            ingestion_run_id,
            calculation_version,
        )

        cash = instants["cash_and_equivalents"]
        debt = _total_debt(
            instants["total_debt"], instants["short_term_debt"], instants["long_term_debt"]
        )
        net_debt = _subtract(debt, cash, "total_debt_mrq - cash_and_equivalents_mrq")
        _add_instant_value(
            rows,
            sid,
            "fundamentals.financial_health.cash_and_equivalents_mrq",
            "financial_health",
            cash,
            ingestion_run_id,
            calculation_version,
        )
        _add_instant_value(
            rows,
            sid,
            "fundamentals.financial_health.total_debt_mrq",
            "financial_health",
            debt,
            ingestion_run_id,
            calculation_version,
        )
        _add_instant_value(
            rows,
            sid,
            "fundamentals.financial_health.net_debt_mrq",
            "financial_health",
            net_debt,
            ingestion_run_id,
            calculation_version,
        )
        _add_ratio(
            rows,
            sid,
            "fundamentals.financial_health.net_debt_to_ebitda_ttm",
            "financial_health",
            net_debt,
            ttm["ebitda"],
            "multiple",
            "net_debt_mrq / ebitda_ttm",
            ingestion_run_id,
            calculation_version,
        )
        _add_ratio(
            rows,
            sid,
            "fundamentals.financial_health.current_ratio_mrq",
            "financial_health",
            instants["current_assets"],
            instants["current_liabilities"],
            "multiple",
            "current_assets / current_liabilities",
            ingestion_run_id,
            calculation_version,
        )
        _add_ratio(
            rows,
            sid,
            "fundamentals.financial_health.debt_to_equity_mrq",
            "financial_health",
            debt,
            instants["total_equity"],
            "multiple",
            "total_debt / total_equity",
            ingestion_run_id,
            calculation_version,
        )

    if not rows:
        return _empty_output()
    df = pl.DataFrame(rows)
    df = compute_version_hash(df)
    if "normalization_version" in df.columns:
        df = df.drop("normalization_version")
    df = df.with_columns(
        pl.col("currency").cast(pl.String),
        pl.col("source_currency").cast(pl.String),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("period_end").cast(pl.Date),
    )
    return FundamentalMetricFact.validate(df)


_FLOW_ITEMS = (
    "revenue",
    "gross_profit",
    "operating_income",
    "net_income",
    "diluted_eps",
    "ebitda",
    "operating_cash_flow",
    "capital_expenditure",
)
_GROWTH_ITEMS = ("revenue", "diluted_eps", "ebitda")
_INSTANT_ITEMS = (
    "cash_and_equivalents",
    "current_assets",
    "current_liabilities",
    "total_equity",
    "short_term_debt",
    "long_term_debt",
    "total_debt",
)


def _latest_facts(facts: pl.DataFrame) -> list[dict[str, Any]]:
    selected: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in facts.rows(named=True):
        key = (
            row["security_id"],
            row["period_kind"],
            row["period_end"],
            row["measurement_kind"],
            row["statement_type"],
            row["line_item"],
        )
        cur = selected.get(key)
        if cur is None or _is_preferred(row, cur):
            selected[key] = row
    return list(selected.values())


def _is_preferred(new: dict[str, Any], old: dict[str, Any]) -> bool:
    new_priority = _source_priority(new)
    old_priority = _source_priority(old)
    if new_priority != old_priority:
        return new_priority < old_priority
    return new["available_at"] > old["available_at"]


def _source_priority(row: dict[str, Any]) -> int:
    value = row.get("source_priority")
    return int(value) if value is not None else 999


def _standalone_quarter_flows(facts: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_item: dict[str, list[dict[str, Any]]] = {item: [] for item in _FLOW_ITEMS}
    annual_by_item_year: dict[tuple[str, int], dict[str, Any]] = {}
    q_by_item_year: dict[tuple[str, int], dict[int, dict[str, Any]]] = {}

    for row in facts:
        if row["measurement_kind"] != "flow" or row["line_item"] not in _FLOW_ITEMS:
            continue
        item = row["line_item"]
        year = _fiscal_year(row.get("fiscal_period", ""), row["period_end"])
        if row["period_kind"] == "quarter":
            by_item[item].append(row)
            q = _quarter_number(row.get("fiscal_period", ""))
            if q is not None:
                q_by_item_year.setdefault((item, year), {})[q] = row
        elif row["period_kind"] == "fiscal_year":
            annual_by_item_year[(item, year)] = row

    for (item, year), annual in annual_by_item_year.items():
        quarters = q_by_item_year.get((item, year), {})
        if 4 in quarters or not {1, 2, 3}.issubset(quarters):
            continue
        derived = _derive_q4(annual, [quarters[1], quarters[2], quarters[3]])
        by_item[item].append(derived)

    for item, rows in by_item.items():
        by_item[item] = sorted(rows, key=lambda r: r["period_end"])
    return by_item


def _derive_q4(annual: dict[str, Any], first_three: list[dict[str, Any]]) -> dict[str, Any]:
    value = float(annual["value"]) - sum(float(q["value"]) for q in first_three)
    source_rows = [*first_three, annual]
    return {
        **annual,
        "period_kind": "quarter",
        "fiscal_period": f"{_fiscal_year(annual.get('fiscal_period', ''), annual['period_end'])}Q4",
        "value": value,
        "available_at": max(r["available_at"] for r in source_rows),
        "_source_period_ends": [r["period_end"] for r in source_rows],
        "_source_version_hashes": [r["version_hash"] for r in source_rows],
        "_calculation_basis": "derived_q4_from_fiscal_year_minus_q1_q2_q3",
    }


def _latest_ttm(quarters: dict[str, list[dict[str, Any]]], item: str) -> dict[str, Any] | None:
    rows = quarters.get(item, [])
    if len(rows) < 4:
        return None
    return _aggregate(rows[-4:], "sum_last_four_standalone_quarters")


def _prior_ttm(quarters: dict[str, list[dict[str, Any]]], item: str) -> dict[str, Any] | None:
    rows = quarters.get(item, [])
    if len(rows) < 8:
        return None
    return _aggregate(rows[-8:-4], "sum_prior_four_standalone_quarters")


def _aggregate(rows: list[dict[str, Any]], basis: str) -> dict[str, Any]:
    if rows and rows[0]["line_item"] == "capital_expenditure":
        value = sum(abs(float(r["value"])) for r in rows)
    else:
        value = sum(float(r["value"]) for r in rows)
    return {
        "value": value,
        "period_kind": "ttm",
        "period_end": rows[-1]["period_end"],
        "available_at": max(r["available_at"] for r in rows),
        "currency": _same_or_none(r.get("currency") for r in rows),
        "source_currency": _same_or_none(r.get("source_currency") for r in rows),
        "source_period_ends": _periods(rows),
        "source_version_hashes": _hashes(rows),
        "calculation_basis": basis,
    }


def _latest_instant(facts: list[dict[str, Any]], item: str) -> dict[str, Any] | None:
    rows = [
        r
        for r in facts
        if r["measurement_kind"] == "instant"
        and r["line_item"] == item
        and r["period_kind"] in ("quarter", "fiscal_year", "mrq")
    ]
    if not rows:
        return None
    row = sorted(rows, key=lambda r: (r["period_end"], r["available_at"]))[-1]
    return {
        "value": float(row["value"]),
        "period_kind": "mrq",
        "period_end": row["period_end"],
        "available_at": row["available_at"],
        "currency": row.get("currency"),
        "source_currency": row.get("source_currency"),
        "source_period_ends": _periods([row]),
        "source_version_hashes": _hashes([row]),
        "calculation_basis": "latest_available_instant_fact",
    }


def _free_cash_flow(
    ocf: dict[str, Any] | None, capex: dict[str, Any] | None
) -> dict[str, Any] | None:
    if ocf is None or capex is None:
        return None
    value = float(ocf["value"]) - float(capex["value"])
    return _combine(
        value,
        "ttm",
        max(ocf["period_end"], capex["period_end"]),
        [ocf, capex],
        "operating_cash_flow_ttm - normalized_capital_expenditure_ttm",
    )


def _total_debt(
    total: dict[str, Any] | None, short: dict[str, Any] | None, long: dict[str, Any] | None
) -> dict[str, Any] | None:
    if total is not None:
        return total
    if short is None or long is None:
        return None
    return _combine(
        float(short["value"]) + float(long["value"]),
        "mrq",
        max(short["period_end"], long["period_end"]),
        [short, long],
        "short_term_debt + long_term_debt",
    )


def _subtract(
    left: dict[str, Any] | None, right: dict[str, Any] | None, basis: str
) -> dict[str, Any] | None:
    if left is None or right is None:
        return None
    return _combine(
        float(left["value"]) - float(right["value"]),
        "mrq",
        max(left["period_end"], right["period_end"]),
        [left, right],
        basis,
    )


def _combine(
    value: float, period_kind: str, period_end: date, parts: list[dict[str, Any]], basis: str
) -> dict[str, Any]:
    return {
        "value": value,
        "period_kind": period_kind,
        "period_end": period_end,
        "available_at": max(p["available_at"] for p in parts),
        "currency": _same_or_none(p.get("currency") for p in parts),
        "source_currency": _same_or_none(p.get("source_currency") for p in parts),
        "source_period_ends": [d for p in parts for d in p["source_period_ends"]],
        "source_version_hashes": [h for p in parts for h in p["source_version_hashes"]],
        "calculation_basis": basis,
    }


def _add_ttm_value(
    rows: list[dict[str, Any]],
    sid: str,
    metric_id: str,
    category: str,
    item: dict[str, Any] | None,
    run_id: str,
    calc_version: str,
) -> None:
    if item is not None:
        rows.append(
            _metric_row(
                sid, metric_id, category, item, item["value"], "currency", run_id, calc_version
            )
        )


def _add_instant_value(
    rows: list[dict[str, Any]],
    sid: str,
    metric_id: str,
    category: str,
    item: dict[str, Any] | None,
    run_id: str,
    calc_version: str,
) -> None:
    if item is not None:
        rows.append(
            _metric_row(
                sid, metric_id, category, item, item["value"], "currency", run_id, calc_version
            )
        )


def _add_ratio(
    rows: list[dict[str, Any]],
    sid: str,
    metric_id: str,
    category: str,
    numerator: dict[str, Any] | None,
    denominator: dict[str, Any] | None,
    unit: str,
    basis: str,
    run_id: str,
    calc_version: str,
    *,
    scale: float = 1.0,
) -> None:
    if numerator is None or denominator is None:
        return
    combined = _combine(
        0.0,
        numerator["period_kind"],
        max(numerator["period_end"], denominator["period_end"]),
        [numerator, denominator],
        basis,
    )
    denom = float(denominator["value"])
    if denom <= 0:
        rows.append(
            _metric_row(
                sid,
                metric_id,
                category,
                combined,
                None,
                unit,
                run_id,
                calc_version,
                quality_status="not_meaningful",
            )
        )
        return
    rows.append(
        _metric_row(
            sid,
            metric_id,
            category,
            combined,
            float(numerator["value"]) / denom * scale,
            unit,
            run_id,
            calc_version,
        )
    )


def _add_growth(
    rows: list[dict[str, Any]],
    sid: str,
    metric_id: str,
    category: str,
    current: dict[str, Any] | None,
    prior: dict[str, Any] | None,
    basis: str,
    run_id: str,
    calc_version: str,
) -> None:
    if current is None or prior is None:
        return
    combined = _combine(0.0, "ttm", current["period_end"], [current, prior], basis)
    base = float(prior["value"])
    if base <= 0:
        rows.append(
            _metric_row(
                sid,
                metric_id,
                category,
                combined,
                None,
                "percent",
                run_id,
                calc_version,
                quality_status="not_meaningful",
            )
        )
        return
    rows.append(
        _metric_row(
            sid,
            metric_id,
            category,
            combined,
            (float(current["value"]) / base - 1.0) * 100.0,
            "percent",
            run_id,
            calc_version,
        )
    )


def _metric_row(
    sid: str,
    metric_id: str,
    category: str,
    item: dict[str, Any],
    value: float | None,
    unit: str,
    run_id: str,
    calc_version: str,
    *,
    quality_status: str = "valid",
) -> dict[str, Any]:
    return {
        "security_id": sid,
        "metric_id": metric_id,
        "metric_version": METRIC_VERSION,
        "category": category,
        "period_kind": item["period_kind"],
        "period_end": item["period_end"],
        "available_at": item["available_at"],
        "value": value,
        "unit": unit,
        "currency": item.get("currency") if unit == "currency" else None,
        "source_currency": item.get("source_currency"),
        "source_period_ends": _json_dates(item["source_period_ends"]),
        "source_version_hashes": _json_strings(item["source_version_hashes"]),
        "calculation_basis": item["calculation_basis"],
        "quality_status": quality_status,
        "calculation_version": calc_version,
        "ingestion_run_id": run_id,
        "source_id": "derived",
        "source_fetch_id": "",
        "raw_payload_hash": "",
        "content_hash": "",
        "version_hash": "",
        "schema_version": 1,
        "parser_version": 1,
    }


def _periods(rows: list[dict[str, Any]]) -> list[date]:
    periods: list[date] = []
    for row in rows:
        periods.extend(row.get("_source_period_ends", [row["period_end"]]))
    return periods


def _hashes(rows: list[dict[str, Any]]) -> list[str]:
    hashes: list[str] = []
    for row in rows:
        hashes.extend(row.get("_source_version_hashes", [row["version_hash"]]))
    return hashes


def _json_dates(values: Iterable[date]) -> str:
    return json.dumps([v.isoformat() for v in values], separators=(",", ":"))


def _json_strings(values: Iterable[str]) -> str:
    return json.dumps(list(values), separators=(",", ":"))


def _same_or_none(values: Iterable[Any]) -> str | None:
    non_null = [str(v) for v in values if v is not None]
    return non_null[0] if non_null and all(v == non_null[0] for v in non_null) else None


def _quarter_number(fiscal_period: str) -> int | None:
    match = re.search(r"Q([1-4])", fiscal_period.upper())
    return int(match.group(1)) if match else None


def _fiscal_year(fiscal_period: str, period_end: date) -> int:
    match = re.search(r"(20\d{2}|19\d{2})", fiscal_period)
    return int(match.group(1)) if match else period_end.year


def compute_estimate_metrics(
    estimates: pl.DataFrame,
    earnings: pl.DataFrame,
    as_of: datetime,
    *,
    ingestion_run_id: str = "",
    calculation_version: str = CALCULATION_VERSION,
) -> pl.DataFrame:
    """Compute estimate and event metrics from analyst estimates and earnings calendar data.

    Parameters
    ----------
    estimates
        Canonical ``AnalystEstimateFact``-shaped rows, pre-filtered to PIT boundary.
    earnings
        Canonical ``EarningsEventFact``-shaped rows, pre-filtered to PIT boundary.
    as_of
        The knowledge timestamp for PIT resolution.
    """
    if estimates.is_empty() and earnings.is_empty():
        return _empty_output()

    rows: list[dict[str, Any]] = []

    if not estimates.is_empty():
        estimates = estimates.filter(pl.col("available_at") <= as_of)
    if not earnings.is_empty():
        earnings = earnings.filter(pl.col("available_at") <= as_of)

    # ── Estimate metrics ────────────────────────────────────────────────
    if not estimates.is_empty():
        est_sids = sorted({str(r["security_id"]) for r in estimates.rows(named=True)})
        for sid in est_sids:
            sid_df = estimates.filter(pl.col("security_id") == sid)
            pe = _pick_latest_estimate(sid_df)
            if pe is None:
                continue
            ts = pe["available_at"]
            item = _snapshot_item(pe["effective_date"], ts)

            # target_price
            if pe.get("target_mean") is not None:
                rows.append(
                    _metric_row(
                        sid,
                        "fundamentals.estimates.target_price",
                        "Estimates",
                        item,
                        float(pe["target_mean"]),
                        "currency",
                        ingestion_run_id,
                        calculation_version,
                    )
                )
            # target_high
            if pe.get("target_high") is not None:
                rows.append(
                    _metric_row(
                        sid,
                        "fundamentals.estimates.target_high",
                        "Estimates",
                        item,
                        float(pe["target_high"]),
                        "currency",
                        ingestion_run_id,
                        calculation_version,
                    )
                )
            # target_low
            if pe.get("target_low") is not None:
                rows.append(
                    _metric_row(
                        sid,
                        "fundamentals.estimates.target_low",
                        "Estimates",
                        item,
                        float(pe["target_low"]),
                        "currency",
                        ingestion_run_id,
                        calculation_version,
                    )
                )
            # buy_ratio
            _add_estimate_buy_ratio(rows, sid, pe, item, ingestion_run_id, calculation_version)

    # ── Event metrics ───────────────────────────────────────────────────
    if not earnings.is_empty():
        earn_sids = sorted({str(r["security_id"]) for r in earnings.rows(named=True)})
        for sid in earn_sids:
            sid_df = earnings.filter(pl.col("security_id") == sid)
            next_rows = sid_df.filter(pl.col("report_date") > as_of.date()).sort("report_date")
            if next_rows.is_empty():
                continue
            rd = next_rows["report_date"][0]
            if rd is None:
                continue
            ptr = next_rows["available_at"][0]
            item = _snapshot_item(rd, ptr if isinstance(ptr, datetime) else as_of)
            days = (rd - as_of.date()).days
            rows.append(
                _metric_row(
                    sid,
                    "fundamentals.events.days_to_earnings",
                    "Events",
                    item,
                    float(days),
                    "days",
                    ingestion_run_id,
                    calculation_version,
                )
            )

    if not rows:
        return _empty_output()
    df = pl.DataFrame(rows)
    df = compute_version_hash(df)
    if "normalization_version" in df.columns:
        df = df.drop("normalization_version")
    df = df.with_columns(
        pl.col("currency").cast(pl.String),
        pl.col("source_currency").cast(pl.String),
        pl.col("period_end").cast(pl.Date),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
    )
    return FundamentalMetricFact.validate(df)


def _pick_latest_estimate(df: pl.DataFrame) -> dict[str, Any] | None:
    """Pick the latest estimate row by effective_date and available_at."""
    sorted_df = df.sort(["effective_date", "available_at"], descending=True)
    row = sorted_df.rows(named=True)
    return row[0] if row else None


def _snapshot_item(period_end: date, available_at: datetime) -> dict[str, Any]:
    if not isinstance(period_end, date):
        raise TypeError(f"expected date, got {type(period_end).__name__}")
    if not isinstance(available_at, datetime):
        raise TypeError(f"expected datetime, got {type(available_at).__name__}")
    return {
        "period_kind": "snapshot",
        "period_end": period_end,
        "available_at": available_at,
        "currency": "USD",
        "source_currency": "USD",
        "source_period_ends": [],
        "source_version_hashes": [],
        "calculation_basis": "latest_estimate",
    }


def _add_estimate_buy_ratio(
    rows: list[dict[str, Any]],
    sid: str,
    pe: dict[str, Any],
    item: dict[str, Any],
    run_id: str,
    calc_version: str,
) -> None:
    sb = pe.get("strong_buy", 0)
    b = pe.get("buy", 0)
    h = pe.get("hold", 0)
    s = pe.get("sell", 0)
    ss = pe.get("strong_sell", 0)
    total = sb + b + h + s + ss
    if total <= 0:
        return
    ratio = (sb + b) / total * 100.0
    rows.append(
        _metric_row(
            sid,
            "fundamentals.estimates.buy_ratio",
            "Estimates",
            item,
            ratio,
            "percent",
            run_id,
            calc_version,
        )
    )


def _empty_output() -> pl.DataFrame:
    return pl.DataFrame(
        schema={name: dtype for name, dtype in FundamentalMetricFact.dtypes.items()}
    )
