from pathlib import Path

import polars as pl

from alpha_lake.replay import load_golden_hash, load_golden_output

_FIXTURE_DIR = Path(__file__).parent / "replay" / "fixtures"


def golden_dir() -> Path:
    return _FIXTURE_DIR


def golden_hash() -> str:
    return load_golden_hash(_FIXTURE_DIR)


def golden_output() -> pl.DataFrame:
    return load_golden_output(_FIXTURE_DIR)


def sample_bars_df() -> pl.DataFrame:
    from datetime import date, datetime

    df = pl.DataFrame({
        "security_id": ["sec_aap"], "effective_date": [date(2026, 1, 5)],
        "available_at": [datetime(2026, 1, 5, 16, 0, 0)],
        "source_id": ["eodhd"], "open": [200.0], "high": [205.0], "low": [199.0], "close": [203.5],
        "volume": [5000000], "source_fetch_id": ["f1"], "raw_payload_hash": ["h1"],
        "ingestion_run_id": ["r1"], "content_hash": ["c1"], "version_hash": [""],
        "schema_version": [1], "parser_version": [1], "quality_status": ["valid"],
        "source_published_at": [None], "ingested_at": [None], "validated_at": [None],
    }).with_columns(
        pl.col("source_published_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("ingested_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("validated_at").cast(pl.Datetime(time_zone="UTC")),
    )
    return df


def sample_bars_restated() -> pl.DataFrame:
    from datetime import date, datetime

    df = pl.DataFrame({
        "security_id": ["sec_aap"], "effective_date": [date(2026, 1, 5)],
        "available_at": [datetime(2026, 1, 6, 8, 0, 0)],
        "source_id": ["eodhd"], "open": [201.0], "high": [206.0], "low": [198.0], "close": [204.0],
        "volume": [5100000], "source_fetch_id": ["f2"], "raw_payload_hash": ["h2"],
        "ingestion_run_id": ["r2"], "content_hash": ["c2"], "version_hash": [""],
        "schema_version": [1], "parser_version": [1], "quality_status": ["valid"],
        "source_published_at": [None], "ingested_at": [None], "validated_at": [None],
    }).with_columns(
        pl.col("source_published_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("ingested_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("validated_at").cast(pl.Datetime(time_zone="UTC")),
    )
    return df
