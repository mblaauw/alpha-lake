from datetime import UTC, date, datetime

import polars as pl
import pytest

from alpha_lake.derived.fundamental_metrics import compute_fundamental_period_metrics


def _fact(
    line_item: str,
    value: float,
    period_end: date,
    available_at: datetime,
    *,
    fiscal_period: str,
    measurement_kind: str = "flow",
    period_kind: str = "quarter",
    statement_type: str = "income_statement",
    version_hash: str | None = None,
) -> dict:
    return {
        "security_id": "sec_t",
        "effective_date": period_end,
        "available_at": available_at,
        "source_id": "sec",
        "source_published_at": available_at,
        "ingested_at": available_at,
        "validated_at": available_at,
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
        "source_priority": 1,
        "source_fetch_id": "fetch_1",
        "raw_payload_hash": "raw_1",
        "ingestion_run_id": "run_1",
        "content_hash": "content_1",
        "version_hash": version_hash or f"{line_item}_{period_end.isoformat()}_{value}",
        "schema_version": 1,
        "parser_version": 1,
        "quality_status": "valid",
    }


def _df(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows).with_columns(
        pl.col("effective_date").cast(pl.Date),
        pl.col("period_end").cast(pl.Date),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("source_published_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("ingested_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("validated_at").cast(pl.Datetime(time_zone="UTC")),
    )


def _quarter_rows(line_item: str, values: list[float], start_year: int = 2024) -> list[dict]:
    dates = [
        date(start_year, 3, 31),
        date(start_year, 6, 30),
        date(start_year, 9, 30),
        date(start_year, 12, 31),
        date(start_year + 1, 3, 31),
        date(start_year + 1, 6, 30),
        date(start_year + 1, 9, 30),
        date(start_year + 1, 12, 31),
    ]
    rows = []
    for idx, value in enumerate(values):
        year = dates[idx].year
        q = idx % 4 + 1
        rows.append(
            _fact(
                line_item,
                value,
                dates[idx],
                datetime(year, q * 3, 15, 12, tzinfo=UTC),
                fiscal_period=f"{year}Q{q}",
            )
        )
    return rows


def _value(df: pl.DataFrame, metric_id: str) -> float | None:
    row = df.filter(pl.col("metric_id") == metric_id)
    assert row.height == 1
    return row["value"][0]


def test_ttm_requires_four_standalone_quarters():
    facts = _df(_quarter_rows("revenue", [10.0, 11.0, 12.0]))
    result = compute_fundamental_period_metrics(
        facts, datetime(2025, 1, 1, tzinfo=UTC), ingestion_run_id="run_1"
    )

    assert result.filter(pl.col("metric_id") == "fundamentals.scale.revenue_ttm").is_empty()


def test_ttm_uses_latest_four_quarters_and_excludes_future_filings():
    rows = _quarter_rows("revenue", [10.0, 11.0, 12.0, 13.0])
    rows.append(
        _fact(
            "revenue",
            100.0,
            date(2025, 3, 31),
            datetime(2025, 5, 15, 12, tzinfo=UTC),
            fiscal_period="2025Q1",
        )
    )
    result = compute_fundamental_period_metrics(
        _df(rows), datetime(2025, 4, 1, tzinfo=UTC), ingestion_run_id="run_1"
    )

    assert _value(result, "fundamentals.scale.revenue_ttm") == pytest.approx(46.0)


def test_later_restatement_does_not_change_prior_as_of_result():
    rows = _quarter_rows("revenue", [10.0, 11.0, 12.0, 13.0])
    rows.append(
        _fact(
            "revenue",
            30.0,
            date(2024, 12, 31),
            datetime(2025, 2, 1, 12, tzinfo=UTC),
            fiscal_period="2024Q4",
            version_hash="restated_q4",
        )
    )
    facts = _df(rows)

    before = compute_fundamental_period_metrics(
        facts, datetime(2025, 1, 15, tzinfo=UTC), ingestion_run_id="run_1"
    )
    after = compute_fundamental_period_metrics(
        facts, datetime(2025, 2, 2, tzinfo=UTC), ingestion_run_id="run_1"
    )

    assert _value(before, "fundamentals.scale.revenue_ttm") == pytest.approx(46.0)
    assert _value(after, "fundamentals.scale.revenue_ttm") == pytest.approx(63.0)


def test_q4_can_be_derived_from_annual_minus_first_three_quarters():
    rows = _quarter_rows("revenue", [10.0, 11.0, 12.0])
    rows.append(
        _fact(
            "revenue",
            50.0,
            date(2024, 12, 31),
            datetime(2025, 2, 1, 12, tzinfo=UTC),
            fiscal_period="2024FY",
            period_kind="fiscal_year",
        )
    )
    result = compute_fundamental_period_metrics(
        _df(rows), datetime(2025, 2, 2, tzinfo=UTC), ingestion_run_id="run_1"
    )

    assert _value(result, "fundamentals.scale.revenue_ttm") == pytest.approx(50.0)
    source_periods = result.filter(pl.col("metric_id") == "fundamentals.scale.revenue_ttm")[
        "source_period_ends"
    ][0]
    assert "2024-12-31" in source_periods


def test_fcf_uses_normalized_capex_sign():
    rows = []
    rows.extend(_quarter_rows("operating_cash_flow", [100.0, 100.0, 100.0, 100.0]))
    rows.extend(_quarter_rows("capital_expenditure", [-10.0, 10.0, -10.0, 10.0]))
    rows.extend(_quarter_rows("net_income", [80.0, 80.0, 80.0, 80.0]))
    result = compute_fundamental_period_metrics(
        _df(rows), datetime(2025, 1, 1, tzinfo=UTC), ingestion_run_id="run_1"
    )

    assert _value(result, "fundamentals.cash_flow_quality.fcf_conversion_ttm") == pytest.approx(
        360.0 / 320.0
    )


def test_mrq_balance_sheet_metrics_use_latest_instant():
    rows = [
        _fact(
            "cash_and_equivalents",
            50.0,
            date(2024, 9, 30),
            datetime(2024, 11, 1, 12, tzinfo=UTC),
            fiscal_period="2024Q3",
            measurement_kind="instant",
            statement_type="balance_sheet",
        ),
        _fact(
            "cash_and_equivalents",
            75.0,
            date(2024, 12, 31),
            datetime(2025, 2, 1, 12, tzinfo=UTC),
            fiscal_period="2024Q4",
            measurement_kind="instant",
            statement_type="balance_sheet",
        ),
    ]
    result = compute_fundamental_period_metrics(
        _df(rows), datetime(2025, 2, 2, tzinfo=UTC), ingestion_run_id="run_1"
    )

    assert _value(
        result, "fundamentals.financial_health.cash_and_equivalents_mrq"
    ) == pytest.approx(75.0)


def test_net_debt_to_ebitda_handles_net_cash_and_negative_ebitda():
    rows = []
    rows.extend(_quarter_rows("ebitda", [10.0, 10.0, 10.0, 10.0]))
    rows.extend(
        [
            _fact(
                "total_debt",
                20.0,
                date(2024, 12, 31),
                datetime(2025, 2, 1, 12, tzinfo=UTC),
                fiscal_period="2024Q4",
                measurement_kind="instant",
                statement_type="balance_sheet",
            ),
            _fact(
                "cash_and_equivalents",
                50.0,
                date(2024, 12, 31),
                datetime(2025, 2, 1, 12, tzinfo=UTC),
                fiscal_period="2024Q4",
                measurement_kind="instant",
                statement_type="balance_sheet",
            ),
        ]
    )
    result = compute_fundamental_period_metrics(
        _df(rows), datetime(2025, 2, 2, tzinfo=UTC), ingestion_run_id="run_1"
    )
    assert _value(result, "fundamentals.financial_health.net_debt_to_ebitda_ttm") == pytest.approx(
        -0.75
    )

    negative = [r for r in rows if r["line_item"] not in {"ebitda"}]
    negative.extend(_quarter_rows("ebitda", [-1.0, -1.0, -1.0, -1.0]))
    result = compute_fundamental_period_metrics(
        _df(negative), datetime(2025, 2, 2, tzinfo=UTC), ingestion_run_id="run_1"
    )
    row = result.filter(
        pl.col("metric_id") == "fundamentals.financial_health.net_debt_to_ebitda_ttm"
    )
    assert row["value"][0] is None
    assert row["quality_status"][0] == "not_meaningful"
