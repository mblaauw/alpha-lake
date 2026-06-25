"""Currency, unit, and numeric normalization rules per DESIGN.md §9.

All monetary values stored in USD with source currency recorded.
All volumes/quantities stored in raw units with unit field.
"""

CURRENCY_CONVERSION: dict[str, float] = {
    "USD": 1.0,
    "EUR": 1.05,
    "GBP": 1.25,
    "JPY": 0.0067,
    "CAD": 0.73,
    "AUD": 0.65,
    "CHF": 1.10,
    "CNY": 0.14,
    "HKD": 0.13,
    "SGD": 0.74,
}

PREFERRED_CURRENCIES: list[str] = ["USD", "EUR", "GBP", "JPY"]


def normalize_value(
    value: float,
    source_currency: str = "USD",
) -> float:
    """Convert a value to standard USD normalization."""
    rate = CURRENCY_CONVERSION.get(source_currency.upper(), 1.0)
    return round(value * rate, 6)


def standardize_line_item(raw: str) -> str:
    """Normalize a line item name to a standard key."""
    mapping = {
        "assets": "total_assets",
        "capital expenditure": "capital_expenditure",
        "cash and cash equivalents": "cash_and_equivalents",
        "cash and equivalents": "cash_and_equivalents",
        "cost of revenue": "cost_of_revenue",
        "current assets": "current_assets",
        "current liabilities": "current_liabilities",
        "depreciation and amortization": "depreciation_amortization",
        "depreciation amortization": "depreciation_amortization",
        "diluted eps": "diluted_eps",
        "diluted weighted average shares": "diluted_weighted_average_shares",
        "dividends paid": "dividends_paid",
        "earnings per share": "diluted_eps",
        "ebitda": "ebitda",
        "eps": "diluted_eps",
        "gross profit": "gross_profit",
        "interest expense": "interest_expense",
        "liabilities": "total_liabilities",
        "long term debt": "long_term_debt",
        "minority interest": "minority_interest",
        "net income": "net_income",
        "netincome": "net_income",
        "operating cash flow": "operating_cash_flow",
        "operating income": "operating_income",
        "preferred equity": "preferred_equity",
        "research and development": "research_and_development",
        "revenue": "revenue",
        "share issuance": "share_issuance",
        "share repurchases": "share_repurchases",
        "shares outstanding": "shares_outstanding",
        "shareholders equity": "total_equity",
        "short term debt": "short_term_debt",
        "stockholders equity": "total_equity",
        "total assets": "total_assets",
        "total debt": "total_debt",
        "total equity": "total_equity",
        "total liabilities": "total_liabilities",
        "total revenue": "revenue",
    }
    return mapping.get(raw.strip().lower(), raw.strip())
