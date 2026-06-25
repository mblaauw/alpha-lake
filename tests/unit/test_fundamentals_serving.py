from datetime import UTC, date, datetime

import duckdb
import polars as pl
import pytest

from alpha_lake.canonical import write_bars, write_dataset
from alpha_lake.kernel import register_kernel
from alpha_lake.serving import read_fundamental_metrics_asof


def _metric(
    metric_id: str,
    value: float | None,
    period_end: date,
    available_at: datetime,
    *,
    category: str = "profitability",
    unit: str = "percent",
    currency: str | None = None,
    quality_status: str = "valid",
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "security_id": ["sec_t"],
            "metric_id": [metric_id],
            "metric_version": ["1.0.0"],
            "category": [category],
            "period_kind": ["ttm"],
            "period_end": [period_end],
            "available_at": [available_at],
            "value": [value],
            "unit": [unit],
            "currency": [currency],
            "source_currency": [currency],
            "source_period_ends": ['["2025-03-31"]'],
            "source_version_hashes": ['["h1"]'],
            "calculation_basis": ["test_fixture"],
            "quality_status": [quality_status],
            "calculation_version": ["1.0.0"],
            "ingestion_run_id": ["run_1"],
            "source_id": ["derived"],
            "source_fetch_id": [""],
            "raw_payload_hash": [""],
            "content_hash": [""],
            "version_hash": [""],
            "schema_version": [1],
            "parser_version": [1],
        }
    ).with_columns(
        pl.col("currency").cast(pl.String),
        pl.col("source_currency").cast(pl.String),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
    )


def _bar(close: float, effective_date: date, available_at: datetime) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "security_id": ["sec_t"],
            "effective_date": [effective_date],
            "available_at": [available_at],
            "source_id": ["eodhd"],
            "open": [close],
            "high": [close],
            "low": [close],
            "close": [close],
            "volume": [1000],
            "source_fetch_id": [""],
            "raw_payload_hash": [""],
            "ingestion_run_id": ["run_1"],
            "content_hash": [""],
            "version_hash": [""],
            "schema_version": [1],
            "parser_version": [1],
            "quality_status": ["valid"],
            "source_published_at": [None],
            "ingested_at": [None],
            "validated_at": [None],
        }
    ).with_columns(
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("source_published_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("ingested_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("validated_at").cast(pl.Datetime(time_zone="UTC")),
    )


def _con() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("SET timezone = 'UTC'")
    register_kernel(con)
    return con


def _value(df: pl.DataFrame, metric_id: str) -> float | None:
    row = df.filter(pl.col("metric_id") == metric_id)
    assert row.height == 1
    return row["value"][0]


def test_fundamental_reader_requires_as_of():
    con = _con()
    with pytest.raises(ValueError, match="as_of is required"):
        read_fundamental_metrics_asof(con, ["sec_t"], None)
    con.close()


def test_fundamental_reader_excludes_unavailable_filings():
    con = _con()
    write_dataset(
        con,
        "fundamental_metrics",
        _metric(
            "fundamentals.profitability.gross_margin_ttm",
            40.0,
            date(2025, 3, 31),
            datetime(2025, 5, 15, tzinfo=UTC),
        ),
    )

    result = read_fundamental_metrics_asof(con, ["sec_t"], datetime(2025, 5, 1, tzinfo=UTC))

    assert result.is_empty()
    con.close()


def test_fundamental_reader_preserves_restatement_visibility():
    con = _con()
    metric_id = "fundamentals.profitability.gross_margin_ttm"
    write_dataset(
        con,
        "fundamental_metrics",
        _metric(metric_id, 40.0, date(2025, 3, 31), datetime(2025, 5, 1, tzinfo=UTC)),
    )
    write_dataset(
        con,
        "fundamental_metrics",
        _metric(metric_id, 45.0, date(2025, 3, 31), datetime(2025, 6, 1, tzinfo=UTC)),
    )

    before = read_fundamental_metrics_asof(con, ["sec_t"], datetime(2025, 5, 15, tzinfo=UTC))
    after = read_fundamental_metrics_asof(con, ["sec_t"], datetime(2025, 6, 15, tzinfo=UTC))

    assert _value(before, metric_id) == pytest.approx(40.0)
    assert _value(after, metric_id) == pytest.approx(45.0)
    con.close()


def test_valuation_uses_price_available_at_requested_as_of():
    con = _con()
    write_dataset(
        con,
        "fundamental_metrics",
        _metric(
            "fundamentals.profitability.diluted_eps_ttm",
            10.0,
            date(2025, 3, 31),
            datetime(2025, 5, 1, tzinfo=UTC),
            category="profitability",
            unit="currency",
            currency="USD",
        ),
    )
    write_bars(con, _bar(100.0, date(2025, 5, 5), datetime(2025, 5, 5, 21, tzinfo=UTC)))
    write_bars(con, _bar(200.0, date(2025, 5, 20), datetime(2025, 5, 20, 21, tzinfo=UTC)))

    result = read_fundamental_metrics_asof(
        con,
        ["sec_t"],
        datetime(2025, 5, 10, tzinfo=UTC),
        categories=["valuation"],
    )

    assert _value(result, "fundamentals.valuation.price_to_earnings_ttm") == pytest.approx(10.0)
    row = result.filter(pl.col("metric_id") == "fundamentals.valuation.price_to_earnings_ttm")
    assert row["price_close"][0] == pytest.approx(100.0)
    assert row["price_effective_date"][0] == date(2025, 5, 5)
    con.close()


def test_valuation_currency_mismatch_without_pit_fx_is_unavailable():
    con = _con()
    write_dataset(
        con,
        "fundamental_metrics",
        _metric(
            "fundamentals.profitability.diluted_eps_ttm",
            10.0,
            date(2025, 3, 31),
            datetime(2025, 5, 1, tzinfo=UTC),
            category="profitability",
            unit="currency",
            currency="EUR",
        ),
    )
    write_bars(con, _bar(100.0, date(2025, 5, 5), datetime(2025, 5, 5, 21, tzinfo=UTC)))

    result = read_fundamental_metrics_asof(
        con,
        ["sec_t"],
        datetime(2025, 5, 10, tzinfo=UTC),
        categories=["valuation"],
    )

    row = result.filter(pl.col("metric_id") == "fundamentals.valuation.price_to_earnings_ttm")
    assert row["state"][0] == "unavailable"
    assert row["tone"][0] == "gray"
    assert row["unavailable_reason"][0] == "currency_mismatch_without_pit_fx"
    con.close()


def test_fundamental_reader_applies_central_threshold_profile():
    con = _con()
    metric_id = "fundamentals.profitability.gross_margin_ttm"
    write_dataset(
        con,
        "fundamental_metrics",
        _metric(metric_id, 40.0, date(2025, 3, 31), datetime(2025, 5, 1, tzinfo=UTC)),
    )

    result = read_fundamental_metrics_asof(con, ["sec_t"], datetime(2025, 5, 10, tzinfo=UTC))
    row = result.filter(pl.col("metric_id") == metric_id)

    assert row["state"][0] == "available"
    assert row["threshold_profile_id"][0] == "profitability_peer_percentile_v1"
    assert row["threshold_state"][0] == "contextual"
    assert row["tone"][0] == "gray"
    assert row["display_value"][0] == "40.00%"
    con.close()


def test_pe_unavailable_for_non_positive_denominator():
    con = _con()
    metric_id = "fundamentals.profitability.diluted_eps_ttm"
    price_metric = "fundamentals.valuation.price_to_earnings_ttm"

    for eps, expected_reason in [
        (0.0, "non_positive_denominator"),
        (-5.0, "non_positive_denominator"),
    ]:
        write_dataset(
            con,
            "fundamental_metrics",
            _metric(
                metric_id,
                eps,
                date(2025, 3, 31),
                datetime(2025, 5, 1, tzinfo=UTC),
                category="profitability",
                unit="currency",
                currency="USD",
            ),
        )
        write_bars(con, _bar(100.0, date(2025, 5, 5), datetime(2025, 5, 5, 21, tzinfo=UTC)))

        result = read_fundamental_metrics_asof(
            con, ["sec_t"], datetime(2025, 5, 10, tzinfo=UTC), categories=["valuation"]
        )

        row = result.filter(pl.col("metric_id") == price_metric)
        assert row["value"][0] is None
        assert row["quality_status"][0] in ("not_meaningful", "unavailable")
        assert row["unavailable_reason"][0] == expected_reason

        con.execute("DELETE FROM fundamental_metrics")
        con.execute("DELETE FROM lake_bars")
    con.close()


def test_ps_uses_revenue_ttm():
    con = _con()
    write_dataset(
        con,
        "fundamental_metrics",
        _metric(
            "fundamentals.scale.revenue_ttm",
            500.0,
            date(2025, 3, 31),
            datetime(2025, 5, 1, tzinfo=UTC),
            category="Scale",
            unit="currency",
            currency="USD",
        ),
    )
    write_dataset(
        con,
        "fundamental_metrics",
        _metric(
            "fundamentals.scale.revenue_per_share_ttm",
            25.0,
            date(2025, 3, 31),
            datetime(2025, 5, 1, tzinfo=UTC),
            category="Scale",
            unit="currency",
            currency="USD",
        ),
    )
    write_bars(con, _bar(200.0, date(2025, 5, 5), datetime(2025, 5, 5, 21, tzinfo=UTC)))

    result = read_fundamental_metrics_asof(
        con, ["sec_t"], datetime(2025, 5, 10, tzinfo=UTC), categories=["valuation"]
    )

    ps = result.filter(pl.col("metric_id") == "fundamentals.valuation.price_to_sales_ttm")
    assert ps.height == 1
    assert ps["value"][0] == pytest.approx(200.0 / 25.0)
    assert ps["quality_status"][0] == "valid"
    con.close()


def test_pit_excludes_metrics_not_yet_available_at_as_of():
    con = _con()
    metric_id = "fundamentals.profitability.gross_margin_ttm"

    write_dataset(
        con,
        "fundamental_metrics",
        _metric(metric_id, 40.0, date(2025, 3, 31), datetime(2025, 5, 1, tzinfo=UTC)),
    )

    before = read_fundamental_metrics_asof(con, ["sec_t"], datetime(2025, 4, 1, tzinfo=UTC))
    assert before.filter(pl.col("metric_id") == metric_id).is_empty()

    after = read_fundamental_metrics_asof(con, ["sec_t"], datetime(2025, 5, 15, tzinfo=UTC))
    assert not after.filter(pl.col("metric_id") == metric_id).is_empty()
    con.close()
