from datetime import UTC, date, datetime

import duckdb
import polars as pl

from alpha_lake.canonical import DATASETS, compute_version_hash, write_dataset
from alpha_lake.models.fundamental_metric_fact import FundamentalMetricFact


def _metric_df(**overrides) -> pl.DataFrame:
    data = {
        "security_id": ["sec_t"],
        "metric_id": ["fundamentals.profitability.gross_margin_ttm"],
        "metric_version": ["1.0.0"],
        "category": ["profitability"],
        "period_kind": ["ttm"],
        "period_end": [date(2025, 3, 29)],
        "available_at": [datetime(2025, 5, 2, 20, 15, tzinfo=UTC)],
        "value": [0.684],
        "unit": ["percent"],
        "currency": [None],
        "source_currency": [None],
        "source_period_ends": ['["2024-06-29","2024-09-28","2024-12-28","2025-03-29"]'],
        "source_version_hashes": ['["h1","h2","h3","h4"]'],
        "calculation_basis": ["gross_profit_ttm / revenue_ttm"],
        "quality_status": ["valid"],
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
    for key, value in overrides.items():
        data[key] = [value]
    return pl.DataFrame(data).with_columns(
        pl.col("currency").cast(pl.String),
        pl.col("source_currency").cast(pl.String),
    )


def test_fundamental_metric_fact_validates_long_form_observation():
    df = _metric_df()
    validated = FundamentalMetricFact.validate(df)

    assert validated.height == 1
    assert validated["metric_id"][0] == "fundamentals.profitability.gross_margin_ttm"
    assert validated["source_version_hashes"][0] == '["h1","h2","h3","h4"]'


def test_fundamental_metric_dataset_registered():
    assert "fundamental_metrics" in DATASETS
    ds = DATASETS["fundamental_metrics"]
    assert ds.table == "fundamental_metrics"
    assert ds.model is FundamentalMetricFact
    assert ds.natural_keys == ("security_id", "metric_id", "period_kind", "period_end")


def test_write_fundamental_metrics_preserves_restatement_versions():
    con = duckdb.connect()
    con.execute("SET timezone = 'UTC'")
    first = _metric_df(value=0.68, available_at=datetime(2025, 5, 2, 20, 15, tzinfo=UTC))
    restated = _metric_df(
        value=0.69,
        available_at=datetime(2025, 6, 10, 20, 15, tzinfo=UTC),
        source_version_hashes='["h1","h2","h3","h4r"]',
    )

    assert write_dataset(con, "fundamental_metrics", first) == 1
    assert write_dataset(con, "fundamental_metrics", restated) == 1

    rows = con.execute(
        """
        SELECT value, available_at, source_version_hashes, version_hash
        FROM fundamental_metrics
        ORDER BY available_at
        """
    ).fetchall()
    assert [row[0] for row in rows] == [0.68, 0.69]
    assert rows[0][2] == '["h1","h2","h3","h4"]'
    assert rows[0][3] != rows[1][3]
    con.close()


def test_fundamental_metric_version_hash_is_stable_for_column_order():
    df = _metric_df()
    reordered = df.select(list(reversed(df.columns)))

    h1 = compute_version_hash(df)["version_hash"][0]
    h2 = compute_version_hash(reordered)["version_hash"][0]

    assert h1 == h2
