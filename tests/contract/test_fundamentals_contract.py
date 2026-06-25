from pathlib import Path


def test_fundamentals_contract_documents_canonical_semantics():
    contract = Path("contracts/fundamentals.v1.yaml").read_text()

    for field in (
        "period_kind",
        "period_end",
        "measurement_kind",
        "source_currency",
        "source_priority",
        "available_at",
        "version_hash",
    ):
        assert field in contract

    for line_item in (
        "revenue",
        "operating_cash_flow",
        "capital_expenditure",
        "cash_and_equivalents",
        "total_debt",
        "shares_outstanding",
    ):
        assert line_item in contract

    assert "measurement_kind: [flow, instant]" in contract
    assert "period_kind: [quarter, fiscal_year, ttm, mrq]" in contract
    assert "Source precedence is registry-driven" in contract
