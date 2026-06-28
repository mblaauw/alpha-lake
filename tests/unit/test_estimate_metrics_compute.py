from __future__ import annotations

from datetime import UTC, date, datetime

import polars as pl
import pytest

from alpha_lake.derived.fundamental_metrics import compute_estimate_metrics


def _est_row(
    security_id: str,
    effective_date: date,
    available_at: datetime,
    *,
    target_mean: float | None = 150.0,
    target_high: float | None = 200.0,
    target_low: float | None = 100.0,
    strong_buy: int = 5,
    buy: int = 3,
    hold: int = 2,
    sell: int = 0,
    strong_sell: int = 0,
) -> dict:
    return {
        "security_id": security_id,
        "effective_date": effective_date,
        "available_at": available_at,
        "source_id": "fmp",
        "strong_buy": strong_buy,
        "buy": buy,
        "hold": hold,
        "sell": sell,
        "strong_sell": strong_sell,
        "target_mean": target_mean,
        "target_high": target_high,
        "target_low": target_low,
        "source_fetch_id": "f1",
        "raw_payload_hash": "r1",
        "ingestion_run_id": "r1",
        "content_hash": "c1",
        "version_hash": "v1",
        "schema_version": 1,
        "parser_version": 1,
        "quality_status": "valid",
    }


def _earn_row(
    security_id: str,
    report_date: date,
    available_at: datetime,
) -> dict:
    return {
        "security_id": security_id,
        "effective_date": report_date,
        "available_at": available_at,
        "source_id": "eodhd",
        "report_date": report_date,
        "session": "afternoon",
        "source_fetch_id": "f1",
        "raw_payload_hash": "r1",
        "ingestion_run_id": "r1",
        "content_hash": "c1",
        "version_hash": "v1",
        "schema_version": 1,
        "parser_version": 1,
        "quality_status": "valid",
    }


def _df(rows: list[dict], *, cast_dates: bool = True) -> pl.DataFrame:
    df = pl.DataFrame(rows)
    if cast_dates and not df.is_empty():
        for col in df.columns:
            if (
                col in ("effective_date", "report_date", "period_end")
                and df[col].dtype == pl.String
            ):
                df = df.with_columns(pl.col(col).str.to_date())
            if col == "available_at" and df[col].dtype == pl.String:
                df = df.with_columns(pl.col(col).str.to_datetime())
    return df


def _value(df: pl.DataFrame, metric_id: str) -> float | None:
    row = df.filter(pl.col("metric_id") == metric_id)
    assert row.height == 1, f"expected 1 row for {metric_id}, got {row.height}"
    return row["value"][0]


def test_estimates_computes_target_price():
    as_of = datetime(2025, 6, 15, tzinfo=UTC)
    estimates = _df(
        [
            _est_row("SEC_A", date(2025, 6, 1), as_of, target_mean=155.0),
        ]
    )
    result = compute_estimate_metrics(estimates, pl.DataFrame(), as_of, ingestion_run_id="r1")
    assert _value(result, "fundamentals.estimates.target_price") == pytest.approx(155.0)


def test_estimates_computes_buy_ratio():
    as_of = datetime(2025, 6, 15, tzinfo=UTC)
    estimates = _df(
        [
            _est_row(
                "SEC_A", date(2025, 6, 1), as_of, strong_buy=5, buy=3, hold=2, sell=0, strong_sell=0
            ),
        ]
    )
    result = compute_estimate_metrics(estimates, pl.DataFrame(), as_of, ingestion_run_id="r1")
    assert _value(result, "fundamentals.estimates.buy_ratio") == pytest.approx(80.0)


def test_estimates_skips_metric_when_target_is_none():
    as_of = datetime(2025, 6, 15, tzinfo=UTC)
    estimates = _df(
        [
            _est_row("SEC_A", date(2025, 6, 1), as_of, target_mean=None),
        ]
    )
    result = compute_estimate_metrics(estimates, pl.DataFrame(), as_of, ingestion_run_id="r1")
    assert result.filter(pl.col("metric_id") == "fundamentals.estimates.target_price").is_empty()


def test_days_to_earnings_computes_correctly():
    as_of = datetime(2025, 6, 15, tzinfo=UTC)
    earnings = _df(
        [
            _earn_row("SEC_A", date(2025, 7, 1), as_of),
        ]
    )
    result = compute_estimate_metrics(pl.DataFrame(), earnings, as_of, ingestion_run_id="r1")
    assert _value(result, "fundamentals.events.days_to_earnings") == pytest.approx(16.0)


def test_days_to_earnings_excludes_past_reports():
    """Reports before as_of should not be considered 'next'."""
    as_of = datetime(2025, 6, 15, tzinfo=UTC)
    earnings = _df(
        [
            _earn_row("SEC_A", date(2025, 5, 1), as_of),
            _earn_row("SEC_A", date(2025, 7, 1), as_of),
        ]
    )
    result = compute_estimate_metrics(pl.DataFrame(), earnings, as_of, ingestion_run_id="r1")
    assert _value(result, "fundamentals.events.days_to_earnings") == pytest.approx(16.0)


def test_empty_input_returns_empty():
    result = compute_estimate_metrics(
        pl.DataFrame(), pl.DataFrame(), datetime(2025, 6, 15, tzinfo=UTC)
    )
    assert result.is_empty()


def test_pit_filtering_excludes_future_estimates():
    as_of = datetime(2025, 6, 15, tzinfo=UTC)
    estimates = _df(
        [
            _est_row(
                "SEC_A", date(2025, 6, 1), datetime(2025, 6, 20, tzinfo=UTC), target_mean=160.0
            ),
        ]
    )
    result = compute_estimate_metrics(estimates, pl.DataFrame(), as_of, ingestion_run_id="r1")
    assert result.filter(pl.col("metric_id") == "fundamentals.estimates.target_price").is_empty()
