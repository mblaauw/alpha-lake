from __future__ import annotations

from datetime import UTC, date, datetime

import polars as pl
import pytest

from alpha_lake.derived.event_aggregations import (
    compute_attention_deltas,
    compute_insider_cluster_metrics,
    compute_sentiment_ratios,
)


def test_insider_cluster_metrics():
    data = pl.DataFrame(
        {
            "security_id": ["sec_a", "sec_a"],
            "effective_date": [date(2024, 1, 15), date(2024, 1, 20)],
            "available_at": [datetime(2024, 1, 16, tzinfo=UTC)] * 2,
            "transaction_code": ["P", "S"],
            "shares": [100.0, 50.0],
            "value": [5000.0, 3000.0],
            "source_fetch_id": ["", ""],
            "raw_payload_hash": ["", ""],
            "ingestion_run_id": ["", ""],
            "content_hash": ["", ""],
            "version_hash": ["", ""],
        }
    )
    result = compute_insider_cluster_metrics(data, as_of=datetime(2024, 2, 1, tzinfo=UTC))
    assert not result.is_empty()
    assert "buy_count" in result.columns
    assert result["net_value"][0] == 5000.0


def test_attention_deltas():
    data = pl.DataFrame(
        {
            "security_id": ["sec_a", "sec_a"],
            "cohort": ["wsb", "wsb"],
            "effective_date": [date(2024, 1, 15), date(2024, 1, 16)],
            "available_at": [datetime(2024, 1, 16, tzinfo=UTC)] * 2,
            "mentions": [100, 150],
            "rank": [5, 3],
            "source_fetch_id": ["", ""],
            "raw_payload_hash": ["", ""],
            "ingestion_run_id": ["", ""],
            "content_hash": ["", ""],
            "version_hash": ["", ""],
        }
    )
    result = compute_attention_deltas(data, as_of=datetime(2024, 1, 20, tzinfo=UTC))
    assert not result.is_empty()
    delta_rows = result.filter(pl.col("effective_date") == date(2024, 1, 16))
    assert len(delta_rows) == 1
    assert delta_rows["mention_delta_pct"][0] == pytest.approx(50.0)


def test_sentiment_ratios():
    data = pl.DataFrame(
        {
            "security_id": ["sec_a", "sec_a"],
            "effective_date": [date(2024, 1, 15), date(2024, 1, 15)],
            "available_at": [datetime(2024, 1, 16, tzinfo=UTC)] * 2,
            "annotation_kind": ["message_tag", "message_tag"],
            "sentiment_score": [0.5, -0.3],
            "sentiment_label": ["Bullish", "Bearish"],
            "source_fetch_id": ["", ""],
            "raw_payload_hash": ["", ""],
            "ingestion_run_id": ["", ""],
            "content_hash": ["", ""],
            "version_hash": ["", ""],
        }
    )
    result = compute_sentiment_ratios(data, as_of=datetime(2024, 1, 20, tzinfo=UTC))
    assert not result.is_empty()
    assert result["positive_ratio"][0] == 0.5
    assert result["mean_score"][0] == pytest.approx(0.1)


def test_empty_input_insider():
    data = pl.DataFrame(
        schema={
            "security_id": pl.String,
            "effective_date": pl.Date,
            "available_at": pl.Datetime(time_zone="UTC"),
            "transaction_code": pl.String,
            "shares": pl.Float64,
            "value": pl.Float64,
            "source_fetch_id": pl.String,
            "raw_payload_hash": pl.String,
            "ingestion_run_id": pl.String,
            "content_hash": pl.String,
            "version_hash": pl.String,
        }
    )
    result = compute_insider_cluster_metrics(data, as_of=datetime(2024, 2, 1, tzinfo=UTC))
    assert result.is_empty()


def test_empty_input_attention():
    data = pl.DataFrame(
        schema={
            "security_id": pl.String,
            "cohort": pl.String,
            "effective_date": pl.Date,
            "available_at": pl.Datetime(time_zone="UTC"),
            "mentions": pl.Int64,
            "rank": pl.Int64,
            "source_fetch_id": pl.String,
            "raw_payload_hash": pl.String,
            "ingestion_run_id": pl.String,
            "content_hash": pl.String,
            "version_hash": pl.String,
        }
    )
    result = compute_attention_deltas(data, as_of=datetime(2024, 1, 20, tzinfo=UTC))
    assert result.is_empty()


def test_empty_input_sentiment():
    data = pl.DataFrame(
        schema={
            "security_id": pl.String,
            "effective_date": pl.Date,
            "available_at": pl.Datetime(time_zone="UTC"),
            "annotation_kind": pl.String,
            "sentiment_score": pl.Float64,
            "sentiment_label": pl.String,
            "source_fetch_id": pl.String,
            "raw_payload_hash": pl.String,
            "ingestion_run_id": pl.String,
            "content_hash": pl.String,
            "version_hash": pl.String,
        }
    )
    result = compute_sentiment_ratios(data, as_of=datetime(2024, 1, 20, tzinfo=UTC))
    assert result.is_empty()
