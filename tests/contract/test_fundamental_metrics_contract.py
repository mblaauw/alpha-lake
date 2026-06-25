from pathlib import Path


def test_fundamental_metrics_contract_documents_long_form_schema():
    contract = Path("contracts/fundamental_metrics.v1.yaml").read_text()

    for field in (
        "metric_id",
        "metric_version",
        "category",
        "period_kind",
        "period_end",
        "available_at",
        "source_period_ends",
        "source_version_hashes",
        "calculation_basis",
        "calculation_version",
        "version_hash",
    ):
        assert field in contract

    for category in (
        "valuation",
        "profitability",
        "growth",
        "financial_health",
        "cash_flow_quality",
        "capital_allocation",
    ):
        assert category in contract

    assert "One row stores one metric observation" in contract
    assert "Price-linked valuation metrics are read-time calculations" in contract
