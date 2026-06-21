from datetime import date, datetime

import duckdb
import polars as pl

from alpha_lake.canonical import write_bars
from alpha_lake.serving import read_bars_asof


def test_restatement_proof():
    con = duckdb.connect()
    con.execute("SET timezone = 'UTC'")

    df_original = pl.DataFrame(
        {
            "security_id": ["sec_test"],
            "effective_date": [date(2026, 6, 18)],
            "available_at": [datetime(2026, 6, 18, 16, 0, 0)],
            "source_id": ["eodhd"],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [10000],
            "source_fetch_id": [""],
            "raw_payload_hash": [""],
            "ingestion_run_id": [""],
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
        pl.col("source_published_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("ingested_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("validated_at").cast(pl.Datetime(time_zone="UTC")),
    )
    write_bars(con, df_original)

    read_before = read_bars_asof(con, ["sec_test"], datetime(2026, 6, 18, 17, 0, 0))
    assert read_before["close"][0] == 100.5, "original value should be visible before restatement"

    df_restated = pl.DataFrame(
        {
            "security_id": ["sec_test"],
            "effective_date": [date(2026, 6, 18)],
            "available_at": [datetime(2026, 6, 19, 8, 0, 0)],
            "source_id": ["eodhd"],
            "open": [100.0],
            "high": [102.0],
            "low": [99.0],
            "close": [101.0],
            "volume": [10000],
            "source_fetch_id": [""],
            "raw_payload_hash": [""],
            "ingestion_run_id": [""],
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
        pl.col("source_published_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("ingested_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("validated_at").cast(pl.Datetime(time_zone="UTC")),
    )
    write_bars(con, df_restated)

    read_historical = read_bars_asof(con, ["sec_test"], datetime(2026, 6, 18, 17, 0, 0))
    assert read_historical["close"][0] == 100.5, "pre-restatement as_of should see original value"

    read_after = read_bars_asof(con, ["sec_test"], datetime(2026, 6, 19, 12, 0, 0))
    assert read_after["close"][0] == 101.0, "post-restatement as_of should see corrected value"

    assert read_after["version_hash"][0] != read_historical["version_hash"][0], (
        "version_hash should differ"
    )
    con.close()
