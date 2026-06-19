from __future__ import annotations

import hashlib
import json

import duckdb
import polars as pl

from alpha_lake.interop import polars_to_duckdb


def compute_version_hash(df: pl.DataFrame) -> pl.DataFrame:
    row_hashes = []
    for row in df.iter_rows(named=True):
        canonical = {k: row[k] for k in sorted(row.keys()) if k not in ("version_hash",)}
        raw = json.dumps(canonical, sort_keys=True, default=str)
        row_hashes.append(hashlib.sha256(raw.encode()).hexdigest())
    return df.with_columns(pl.Series("version_hash", row_hashes))


def write_bars(con: duckdb.DuckDBPyConnection, df: pl.DataFrame) -> int:
    df = compute_version_hash(df)

    con.execute("""
        CREATE TABLE IF NOT EXISTS lake_bars (
            security_id VARCHAR NOT NULL,
            effective_date DATE NOT NULL,
            available_at TIMESTAMP NOT NULL,
            source_id VARCHAR NOT NULL,
            source_published_at TIMESTAMP,
            ingested_at TIMESTAMP,
            validated_at TIMESTAMP,
            open DOUBLE NOT NULL,
            high DOUBLE NOT NULL,
            low DOUBLE NOT NULL,
            close DOUBLE NOT NULL,
            volume BIGINT NOT NULL,
            source_fetch_id VARCHAR,
            raw_payload_hash VARCHAR,
            ingestion_run_id VARCHAR,
            content_hash VARCHAR,
            version_hash VARCHAR,
            schema_version INT DEFAULT 1,
            parser_version INT DEFAULT 1,
            quality_status VARCHAR DEFAULT 'valid'
        )
    """)

    polars_to_duckdb(con, df, "staging_bars")

    con.execute("""
        INSERT INTO lake_bars
        SELECT
            s.security_id, s.effective_date, s.available_at, s.source_id,
            s.source_published_at, s.ingested_at, s.validated_at,
            s.open, s.high, s.low, s.close, s.volume,
            s.source_fetch_id, s.raw_payload_hash, s.ingestion_run_id,
            s.content_hash, s.version_hash,
            s.schema_version, s.parser_version, s.quality_status
        FROM staging_bars s
        LEFT JOIN lake_bars t
            ON t.security_id = s.security_id
           AND t.effective_date = s.effective_date
           AND t.source_id = s.source_id
           AND t.available_at = s.available_at
           AND t.version_hash = s.version_hash
        WHERE t.security_id IS NULL
    """)

    count = con.execute("SELECT COUNT(*) FROM staging_bars").fetchone()[0]
    con.execute("DROP TABLE IF EXISTS staging_bars")
    return count
