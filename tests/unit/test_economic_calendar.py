from __future__ import annotations

from datetime import UTC, datetime

import polars as pl

from alpha_lake.canonical import DATASETS, compute_version_hash
from alpha_lake.models.economic_calendar_fact import EconomicCalendarFact
from alpha_lake.normalize import economic_calendar_from_json


def test_econ_cal_fact_valid():
    df = pl.DataFrame(
        {
            "event_id": ["fmp_CPI_2025-01-15"],
            "effective_date": ["2025-01-15"],
            "available_at": [datetime(2025, 1, 10, tzinfo=UTC)],
            "source_id": ["fmp"],
            "country": ["US"],
            "source_fetch_id": ["fetch1"],
            "raw_payload_hash": ["h1"],
            "ingestion_run_id": ["run1"],
            "content_hash": ["h1"],
            "version_hash": [""],
            "schema_version": [1],
            "parser_version": [1],
            "quality_status": ["valid"],
        }
    ).with_columns(
        pl.col("effective_date").str.to_date("%Y-%m-%d"),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
    )
    validated = EconomicCalendarFact.validate(df)
    assert len(validated) == 1


def test_econ_cal_registered():
    assert "economic_calendar" in DATASETS
    ds = DATASETS["economic_calendar"]
    assert ds.model is EconomicCalendarFact
    assert "event_id" in ds.natural_keys


def test_normalize_econ_cal():
    raw = [
        {"date": "2025-06-15", "event": "CPI", "country": "US"},
        {"date": "2025-06-18", "event": "FOMC", "country": "US"},
    ]
    df = economic_calendar_from_json(
        raw=raw,
        source_id="fmp",
        source_fetch_id="f1",
        ingestion_run_id="r1",
        content_hash="ch1",
        available_at=datetime(2025, 6, 1, tzinfo=UTC),
    )
    assert len(df) == 2
    assert "CPI" in df["event_id"][0]
    assert str(df["effective_date"][0]) == "2025-06-15"


def test_normalize_skips_empty_rows():
    raw = [
        {"date": "", "event": "", "country": "US"},
        {"date": "2025-07-01", "event": "NFP", "country": "US"},
    ]
    df = economic_calendar_from_json(
        raw=raw,
        source_id="fmp",
        source_fetch_id="f1",
        ingestion_run_id="r1",
        content_hash="ch1",
        available_at=datetime(2025, 6, 1, tzinfo=UTC),
    )
    assert len(df) == 1


def test_version_hash_econ_cal():
    raw = [{"date": "2025-06-15", "event": "CPI", "country": "US"}]
    df = economic_calendar_from_json(
        raw=raw,
        source_id="fmp",
        source_fetch_id="f1",
        ingestion_run_id="r1",
        content_hash="ch1",
        available_at=datetime(2025, 6, 1, tzinfo=UTC),
    )
    df = compute_version_hash(df)
    assert len(df["version_hash"][0]) == 64


def test_econ_cal_stack_config(monkeypatch):
    monkeypatch.delenv("ALPHA_LAKE_CONFIG", raising=False)
    from alpha_lake.config import load_config

    cfg = load_config("config/stack.toml")
    assert "economic_calendar" in cfg.datasets
    assert cfg.datasets["economic_calendar"].tier == "experimental"
    assert cfg.datasets["economic_calendar"].supported is False
    assert cfg.quality["economic_calendar"].max_staleness_days == 7
