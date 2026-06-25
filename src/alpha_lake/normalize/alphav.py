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


def _av_value(val: Any) -> float | None:
    if val is None or val == "None" or val == "":
        return None
    try:
        return float(val)
    except ValueError, TypeError:
        return None


def _parse_date(s: str) -> date | None:
    try:
        return date.fromisoformat(s[:10]) if s else None
    except ValueError, TypeError:
        return None


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
                    rows.append(
                        {
                            "security_id": security_id,
                            "effective_date": period_end,
                            "available_at": available_at,
                            "source_id": source_id,
                            "source_published_at": available_at,
                            "ingested_at": available_at,
                            "validated_at": None,
                            "fiscal_period": fiscal_period,
                            "period_kind": period_kind_label,
                            "period_end": period_end,
                            "measurement_kind": measure_kind,
                            "statement_type": stmt_type,
                            "line_item": line_item,
                            "value": val,
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
