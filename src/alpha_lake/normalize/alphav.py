from __future__ import annotations

from datetime import date, datetime
from typing import Any

import polars as pl

_AV_LINE_ITEM_MAP: dict[str, str] = {
    "totalRevenue": "revenue",
    "grossProfit": "gross_profit",
    "costOfRevenue": "cost_of_revenue",
    "operatingIncome": "operating_income",
    "netIncome": "net_income",
    "ebit": "ebit",
    "ebitda": "ebitda",
    "researchAndDevelopment": "research_development",
    "sellingGeneralAndAdministrative": "selling_general_admin",
    "operatingExpenses": "operating_expense",
    "incomeTaxExpense": "income_tax_expense",
    "depreciationAndAmortization": "depreciation_amortization",
    "interestExpense": "interest_expense",
    "interestIncome": "interest_income",
    "netInterestIncome": "net_interest_income",
    "totalAssets": "total_assets",
    "totalCurrentAssets": "current_assets",
    "cashAndCashEquivalentsAtCarryingValue": "cash_and_equivalents",
    "inventory": "inventory",
    "currentNetReceivables": "accounts_receivable",
    "totalNonCurrentAssets": "non_current_assets",
    "propertyPlantEquipment": "property_plant_equipment",
    "totalLiabilities": "total_liabilities",
    "totalCurrentLiabilities": "current_liabilities",
    "shortTermDebt": "short_term_debt",
    "longTermDebt": "long_term_debt",
    "totalShareholderEquity": "total_equity",
    "retainedEarnings": "retained_earnings",
    "commonStockSharesOutstanding": "shares_outstanding",
    "currentAccountsPayable": "accounts_payable",
    "goodwill": "goodwill",
    "intangibleAssets": "intangible_assets",
    "currentDebt": "short_term_debt",
    "shortLongTermDebtTotal": "total_debt",
    "operatingCashflow": "operating_cash_flow",
    "capitalExpenditures": "capital_expenditure",
    "dividendPayout": "dividends_paid",
    "stockBasedCompensation": "stock_based_compensation",
    "cashflowFromInvestment": "investing_cash_flow",
    "cashflowFromFinancing": "financing_cash_flow",
    "depreciationDepletionAndAmortization": "depreciation_amortization",
    "changeInInventory": "change_in_inventory",
}

_OVERVIEW_FIELDS: dict[str, str] = {
    "MarketCapitalization": "market_capitalization",
    "EnterpriseValue": "enterprise_value",
    "PERatio": "pe_ratio",
    "EPS": "eps",
    "DividendYield": "dividend_yield",
    "BookValue": "book_value",
    "PriceToBookRatio": "pb_ratio",
    "Beta": "beta",
    "ProfitMargin": "profit_margin",
    "RevenueTTM": "revenue_ttm",
    "QuarterlyEarningsGrowthYOY": "earnings_growth_yoy",
    "QuarterlyRevenueGrowthYOY": "revenue_growth_yoy",
    "ReturnOnEquityTTM": "roe",
    "ReturnOnAssetsTTM": "roa",
}


def _av_value(val: Any) -> float | None:
    if val is None or val == "None" or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _parse_date(s: str) -> date | None:
    try:
        return date.fromisoformat(s[:10]) if s else None
    except (ValueError, TypeError):
        return None


def _append_row(
    rows: list[dict[str, Any]],
    security_id: str,
    effective_date: date,
    available_at: datetime,
    source_id: str,
    fiscal_period: str,
    period_kind: str,
    period_end: date,
    measurement_kind: str,
    statement_type: str,
    line_item: str,
    value: float,
    source_fetch_id: str,
    content_hash: str,
    ingestion_run_id: str,
) -> None:
    rows.append(
        {
            "security_id": security_id,
            "effective_date": effective_date,
            "available_at": available_at,
            "source_id": source_id,
            "source_published_at": available_at,
            "ingested_at": available_at,
            "validated_at": None,
            "fiscal_period": fiscal_period,
            "period_kind": period_kind,
            "period_end": period_end,
            "measurement_kind": measurement_kind,
            "statement_type": statement_type,
            "line_item": line_item,
            "value": value,
            "currency": "USD",
            "source_currency": "USD",
            "unit": "raw",
            "source_priority": None,
            "source_fetch_id": source_fetch_id,
            "raw_payload_hash": content_hash,
            "ingestion_run_id": ingestion_run_id,
            "content_hash": content_hash,
            "version_hash": "",
            "schema_version": 1,
            "parser_version": 1,
            "quality_status": "valid",
        }
    )


def fundamentals_from_json(
    raw: list[dict[str, Any]],
    security_id: str,
    source_id: str,
    source_fetch_id: str,
    ingestion_run_id: str,
    content_hash: str,
    available_at: datetime,
) -> pl.DataFrame:
    merged = raw[0] if raw else {}
    rows: list[dict[str, Any]] = []

    stmt_sections = [
        ("incomeStatement", "income_statement", "flow", "quarter"),
        ("balanceSheet", "balance_sheet", "instant", "mrq"),
        ("cashFlow", "cash_flow", "flow", "quarter"),
    ]

    period_keys = {"quarter": "quarterlyReports", "fiscal_year": "annualReports"}

    for section_key, stmt_type, measure_kind, _ in stmt_sections:
        section = merged.get(section_key, {})
        for period_kind_label, pk_var in period_keys.items():
            reports = section.get(pk_var, [])
            if not reports:
                continue
            for report in reports:
                period_end_str = report.get("fiscalDateEnding", "")
                period_end = _parse_date(period_end_str)
                if not period_end:
                    continue
                fiscal_year = period_end.year
                if period_kind_label == "quarter":
                    quarter = (period_end.month - 1) // 3 + 1
                elif period_kind_label == "fiscal_year":
                    quarter = 4
                fiscal_period = f"FY{fiscal_year}Q{quarter}"

                for av_key, line_item in _AV_LINE_ITEM_MAP.items():
                    val = _av_value(report.get(av_key))
                    if val is None:
                        continue
                    _append_row(
                        rows, security_id, period_end, available_at, source_id,
                        fiscal_period, period_kind_label, period_end,
                        measure_kind, stmt_type, line_item, val,
                        source_fetch_id, content_hash, ingestion_run_id,
                    )

    # ── OVERVIEW ────────────────────────────────────────────────────────
    overview = merged.get("overview", {})
    for av_key, line_item in _OVERVIEW_FIELDS.items():
        val = _av_value(overview.get(av_key))
        if val is None:
            continue
        _append_row(
            rows, security_id, available_at.date(), available_at, source_id,
            "OVERVIEW", "snapshot", available_at.date(),
            "overview", "overview", line_item, val,
            source_fetch_id, content_hash, ingestion_run_id,
        )

    # ── SHARES OUTSTANDING ──────────────────────────────────────────────
    so = merged.get("sharesOutstanding", {})
    for pk_label, pk_key in [("quarter", "quarterly"), ("fiscal_year", "annual")]:
        reports = so.get(pk_key, []) if isinstance(so.get(pk_key), list) else []
        for report in reports:
            period_end = _parse_date(report.get("fiscalDateEnding", ""))
            if not period_end:
                continue
            val = _av_value(report.get("sharesOutstanding"))
            if val is None:
                continue
            fy = period_end.year
            q = (period_end.month - 1) // 3 + 1 if pk_label == "quarter" else 4
            _append_row(
                rows, security_id, period_end, available_at, source_id,
                f"FY{fy}Q{q}", pk_label, period_end,
                "overview", "overview", "shares_outstanding", val,
                source_fetch_id, content_hash, ingestion_run_id,
            )

    # ── EARNINGS ────────────────────────────────────────────────────────
    ea = merged.get("earnings", {})
    for pk_label, pk_key in [("quarter", "quarterlyEarnings"), ("fiscal_year", "annualEarnings")]:
        reports = ea.get(pk_key, []) if isinstance(ea.get(pk_key), list) else []
        for report in reports:
            period_end = _parse_date(report.get("fiscalDateEnding", ""))
            if not period_end:
                continue
            fy = period_end.year
            q = (period_end.month - 1) // 3 + 1 if pk_label == "quarter" else 4
            fp = f"FY{fy}Q{q}"

            for av_key, li in [
                ("reportedEPS", "reported_eps"),
                ("estimatedEPS", "estimated_eps"),
                ("surprise", "eps_surprise"),
                ("surprisePercentage", "eps_surprise_pct"),
            ]:
                val = _av_value(report.get(av_key))
                if val is None:
                    continue
                _append_row(
                    rows, security_id, period_end, available_at, source_id,
                    fp, pk_label, period_end,
                    "earnings", "earnings", li, val,
                    source_fetch_id, content_hash, ingestion_run_id,
                )

    # ── EARNINGS ESTIMATES ──────────────────────────────────────────────
    ee = merged.get("earningsEstimates", {})
    for pk_label, pk_key in [("quarter", "quarterly"), ("fiscal_year", "annual")]:
        reports = ee.get(pk_key, []) if isinstance(ee.get(pk_key), list) else []
        for report in reports:
            period_end = _parse_date(report.get("fiscalDateEnding", ""))
            if not period_end:
                continue
            fy = period_end.year
            q = (period_end.month - 1) // 3 + 1 if pk_label == "quarter" else 4
            fp = f"FY{fy}Q{q}"

            for av_key, li in [
                ("estimatedEPS", "estimated_eps"),
                ("estimatedRevenue", "estimated_revenue"),
                ("numberOfAnalysts", "analyst_count"),
            ]:
                val = _av_value(report.get(av_key))
                if val is None:
                    continue
                _append_row(
                    rows, security_id, period_end, available_at, source_id,
                    fp, pk_label, period_end,
                    "earnings", "earnings", li, val,
                    source_fetch_id, content_hash, ingestion_run_id,
                )

    if not rows:
        return pl.DataFrame()
    df = pl.DataFrame(rows)
    return df.with_columns(
        pl.col("effective_date").cast(pl.Date),
        pl.col("period_end").cast(pl.Date),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("source_published_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("ingested_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("validated_at").cast(pl.Datetime(time_zone="UTC")),
    )


def corp_actions_from_json(
    raw: list[dict[str, Any]],
    security_id: str,
    source_id: str,
    source_fetch_id: str,
    ingestion_run_id: str,
    content_hash: str,
    available_at: datetime,
) -> pl.DataFrame:
    """Normalize AV DIVIDENDS and SPLITS into CorpActionFact rows."""
    merged = raw[0] if raw else {}
    rows: list[dict[str, Any]] = []

    div_data = merged.get("dividends", {})
    hist_div = div_data.get("historical", []) or []
    for entry in hist_div:
        ex_date = _parse_date(entry.get("exDividendDate", ""))
        if not ex_date:
            continue
        amt = _av_value(entry.get("dividendAmount"))
        if amt is None:
            continue
        cur = entry.get("currency", "USD")
        rows.append(_corp_row(security_id, ex_date, available_at, source_id,
                              "dividend", None, None, amt, cur,
                              source_fetch_id, content_hash, ingestion_run_id))

    spl_data = merged.get("splits", {})
    hist_spl = spl_data.get("historical", []) or []
    for entry in hist_spl:
        ex_date = _parse_date(entry.get("exDate", ""))
        if not ex_date:
            continue
        ratio = str(entry.get("splitRatio", ""))
        if ":" not in ratio:
            continue
        num, den = ratio.split(":", 1)
        numerator = _av_value(num)
        denominator = _av_value(den)
        if numerator is None or denominator is None:
            continue
        rows.append(_corp_row(security_id, ex_date, available_at, source_id,
                              "split", numerator, denominator, None, None,
                              source_fetch_id, content_hash, ingestion_run_id))

    if not rows:
        return pl.DataFrame()
    df = pl.DataFrame(rows)
    return df.with_columns(
        pl.col("effective_date").cast(pl.Date),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
    )


def _corp_row(
    security_id: str,
    effective_date: date,
    available_at: datetime,
    source_id: str,
    action_type: str,
    ratio_numerator: float | None,
    ratio_denominator: float | None,
    dividend_amount: float | None,
    dividend_currency: str | None,
    source_fetch_id: str,
    content_hash: str,
    ingestion_run_id: str,
) -> dict[str, Any]:
    return {
        "security_id": security_id,
        "effective_date": effective_date,
        "available_at": available_at,
        "source_id": source_id,
        "action_type": action_type,
        "ratio_numerator": ratio_numerator,
        "ratio_denominator": ratio_denominator,
        "dividend_amount": dividend_amount,
        "dividend_currency": dividend_currency,
        "source_fetch_id": source_fetch_id,
        "raw_payload_hash": content_hash,
        "ingestion_run_id": ingestion_run_id,
        "content_hash": content_hash,
        "version_hash": "",
        "schema_version": 1,
        "parser_version": 1,
        "quality_status": "valid",
    }


def insider_transactions_from_json(
    raw: list[dict[str, Any]],
    security_id: str,
    source_id: str,
    source_fetch_id: str,
    ingestion_run_id: str,
    content_hash: str,
    available_at: datetime,
) -> pl.DataFrame:
    """Normalize AV INSIDER_TRANSACTIONS into InsiderTransactionFact rows."""
    merged = raw[0] if raw else {}
    records = merged.get("data", []) if isinstance(merged.get("data"), list) else []
    rows: list[dict[str, Any]] = []
    for entry in records:
        tx_date = _parse_date(entry.get("transaction_date", ""))
        if not tx_date:
            continue
        shares = _av_value(entry.get("shares"))
        price = _av_value(entry.get("share_price"))
        if shares is None:
            continue
        tx_type_raw = (entry.get("acquisition_or_disposal") or "").lower()
        tx_type = "buy" if tx_type_raw.startswith("acq") else "sell"
        rows.append(
            {
                "security_id": security_id,
                "effective_date": tx_date,
                "available_at": available_at,
                "source_id": source_id,
                "transaction_date": tx_date,
                "insider_name": entry.get("executive") or "",
                "insider_title": entry.get("executive_title") or "",
                "transaction_type": tx_type,
                "shares": shares,
                "price": price or 0.0,
                "source_fetch_id": source_fetch_id,
                "raw_payload_hash": content_hash,
                "ingestion_run_id": ingestion_run_id,
                "content_hash": content_hash,
                "version_hash": "",
                "schema_version": 1,
                "parser_version": 1,
                "quality_status": "valid",
            }
        )
    if not rows:
        return pl.DataFrame()
    df = pl.DataFrame(rows)
    return df.with_columns(
        pl.col("effective_date").cast(pl.Date),
        pl.col("transaction_date").cast(pl.Date),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
    )


def institutional_holdings_from_json(
    raw: list[dict[str, Any]],
    security_id: str,
    source_id: str,
    source_fetch_id: str,
    ingestion_run_id: str,
    content_hash: str,
    available_at: datetime,
) -> pl.DataFrame:
    """Normalize AV INSTITUTIONAL_HOLDINGS into InstitutionalHoldingFact rows."""
    merged = raw[0] if raw else {}
    records = merged.get("holdings", []) if isinstance(merged.get("holdings"), list) else []
    rows: list[dict[str, Any]] = []
    for entry in records:
        date_reported = _parse_date(entry.get("date_reported", ""))
        if not date_reported:
            continue
        shares = _av_value(entry.get("shares"))
        value = _av_value(entry.get("value"))
        pct = _av_value(entry.get("percent_change"))
        if shares is None:
            continue
        rows.append(
            {
                "security_id": security_id,
                "effective_date": date_reported,
                "available_at": available_at,
                "source_id": source_id,
                "holder_name": entry.get("holder") or "",
                "shares": shares,
                "value": value,
                "date_reported": date_reported,
                "percent_change": pct,
                "source_fetch_id": source_fetch_id,
                "raw_payload_hash": content_hash,
                "ingestion_run_id": ingestion_run_id,
                "content_hash": content_hash,
                "version_hash": "",
                "schema_version": 1,
                "parser_version": 1,
                "quality_status": "valid",
            }
        )
    if not rows:
        return pl.DataFrame()
    df = pl.DataFrame(rows)
    return df.with_columns(
        pl.col("effective_date").cast(pl.Date),
        pl.col("date_reported").cast(pl.Date),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
    )
