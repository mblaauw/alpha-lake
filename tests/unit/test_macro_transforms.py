from __future__ import annotations

from datetime import UTC, datetime

import polars as pl
import pytest

from alpha_lake.derived.macro_transforms import compute_macro_transforms


def _macro_row(
    series_id: str,
    effective_date: str,
    value: float,
    available_at: datetime | None = None,
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "series_id": [series_id],
            "effective_date": [effective_date],
            "available_at": [available_at or datetime(2024, 1, 1, tzinfo=UTC)],
            "source_id": ["fred"],
            "value": [value],
            "source_fetch_id": [""],
            "raw_payload_hash": [""],
            "ingestion_run_id": [""],
            "content_hash": [""],
            "version_hash": [""],
            "schema_version": [1],
            "parser_version": [1],
            "quality_status": ["valid"],
        }
    ).with_columns(
        pl.col("effective_date").str.to_date("%Y-%m-%d"),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
    )


def test_yoy_computed():
    data = pl.concat(
        [
            _macro_row("CPIAUCSL", "2024-01-01", 110.0),
            _macro_row("CPIAUCSL", "2023-01-01", 100.0),
        ]
    )
    result = compute_macro_transforms(data, as_of=datetime(2024, 1, 15, tzinfo=UTC))
    yoy = result.filter(pl.col("series_id") == "CPIAUCSL_YOY")
    assert len(yoy) == 1
    assert yoy["value"][0] == pytest.approx((110.0 / 100.0) - 1)


def test_mom_computed():
    data = pl.concat(
        [
            _macro_row("UNRATE", "2024-02-01", 4.0),
            _macro_row("UNRATE", "2024-01-01", 3.8),
        ]
    )
    result = compute_macro_transforms(data, as_of=datetime(2024, 2, 15, tzinfo=UTC))
    mom = result.filter(pl.col("series_id") == "UNRATE_MOM")
    assert len(mom) == 1
    assert mom["value"][0] == pytest.approx((4.0 / 3.8) - 1)


def test_transform_not_computed_without_prev():
    data = _macro_row("CPIAUCSL", "2024-01-01", 110.0)
    result = compute_macro_transforms(data, as_of=datetime(2024, 1, 15, tzinfo=UTC))
    assert result.is_empty()


def test_empty_input():
    data = pl.DataFrame(
        schema={
            "series_id": pl.String,
            "effective_date": pl.Date,
            "available_at": pl.Datetime(time_zone="UTC"),
            "source_id": pl.String,
            "value": pl.Float64,
            "source_fetch_id": pl.String,
            "raw_payload_hash": pl.String,
            "ingestion_run_id": pl.String,
            "content_hash": pl.String,
            "version_hash": pl.String,
            "schema_version": pl.Int64,
            "parser_version": pl.Int64,
            "quality_status": pl.String,
        }
    )
    result = compute_macro_transforms(data, as_of=datetime(2024, 1, 15, tzinfo=UTC))
    assert result.is_empty()


def test_transform_pit_bounded():
    """A revision with later available_at should NOT be used for an earlier as_of."""
    data = pl.concat(
        [
            _macro_row(
                "CPIAUCSL", "2024-01-01", 100.0, available_at=datetime(2024, 1, 10, tzinfo=UTC)
            ),
            _macro_row(
                "CPIAUCSL", "2024-01-01", 105.0, available_at=datetime(2024, 2, 1, tzinfo=UTC)
            ),
            _macro_row(
                "CPIAUCSL", "2023-01-01", 90.0, available_at=datetime(2023, 1, 10, tzinfo=UTC)
            ),
        ]
    )

    early_result = compute_macro_transforms(data, as_of=datetime(2024, 1, 15, tzinfo=UTC))
    early_yoy = early_result.filter(pl.col("series_id") == "CPIAUCSL_YOY")
    assert len(early_yoy) == 1
    assert early_yoy["value"][0] == pytest.approx((100.0 / 90.0) - 1)
