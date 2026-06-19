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
        "assets": "Assets",
        "liabilities": "Liabilities",
        "revenue": "Revenue",
        "net income": "NetIncome",
        "netincome": "NetIncome",
        "earnings per share": "EarningsPerShare",
        "eps": "EarningsPerShare",
        "total revenue": "Revenue",
        "gross profit": "GrossProfit",
        "operating income": "OperatingIncome",
        "cash and cash equivalents": "CashAndEquivalents",
        "total assets": "Assets",
        "total liabilities": "Liabilities",
        "stockholders equity": "StockholdersEquity",
        "shareholders equity": "StockholdersEquity",
    }
    return mapping.get(raw.strip().lower(), raw.strip())
