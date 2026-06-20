from __future__ import annotations

import hashlib
import json

import duckdb
import polars as pl

from alpha_lake.interop import polars_to_duckdb

NORMALIZATION_VERSION: int = 1


def compute_version_hash(df: pl.DataFrame) -> pl.DataFrame:
    row_hashes = []
    for row in df.iter_rows(named=True):
        canonical: dict[str, object] = {}
        for k in sorted(row.keys()):
            if k == "version_hash":
                continue
            v = row[k]
            if isinstance(v, float):
                v = round(v, 10)
            canonical[k] = v
        raw = json.dumps(canonical, sort_keys=True, default=str, separators=(",", ":"))
        row_hashes.append(hashlib.sha256(raw.encode()).hexdigest())
    return df.with_columns(
        pl.Series("version_hash", row_hashes),
        pl.lit(NORMALIZATION_VERSION).alias("normalization_version"),
    )


_BARS_DDL = """
    security_id VARCHAR NOT NULL,
    effective_date DATE NOT NULL,
    available_at TIMESTAMPTZ NOT NULL,
    source_id VARCHAR NOT NULL,
    source_published_at TIMESTAMPTZ,
    ingested_at TIMESTAMPTZ,
    validated_at TIMESTAMPTZ,
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
    normalization_version INT DEFAULT 1,
    schema_version INT DEFAULT 1,
    parser_version INT DEFAULT 1,
    quality_status VARCHAR DEFAULT 'valid'
"""


def write_bars(con: duckdb.DuckDBPyConnection, df: pl.DataFrame) -> int:
    df = compute_version_hash(df)
    con.execute(f"CREATE TABLE IF NOT EXISTS lake_bars ({_BARS_DDL})")
    return _merge_into(con, "lake_bars",
        ["security_id", "effective_date", "source_id", "available_at", "version_hash"],
        df)


def write_corp_actions(con: duckdb.DuckDBPyConnection, df: pl.DataFrame) -> int:
    df = compute_version_hash(df)
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS corp_actions (
            security_id VARCHAR NOT NULL, effective_date DATE NOT NULL,
            available_at TIMESTAMPTZ NOT NULL, source_id VARCHAR NOT NULL,
            action_type VARCHAR NOT NULL, ratio_numerator DOUBLE,
            ratio_denominator DOUBLE, dividend_amount DOUBLE, dividend_currency VARCHAR,
            source_fetch_id VARCHAR, raw_payload_hash VARCHAR, ingestion_run_id VARCHAR,
            content_hash VARCHAR, version_hash VARCHAR,
            normalization_version INT DEFAULT 1,
            schema_version INT DEFAULT 1, parser_version INT DEFAULT 1,
            quality_status VARCHAR DEFAULT 'valid'
        )""")
    return _merge_into(con, "corp_actions",
        ["security_id", "action_type", "effective_date", "source_id", "available_at", "version_hash"],
        df)


_DATASET_KEYS: dict[str, list[str]] = {
    "lake_bars": ["security_id", "effective_date", "source_id"],
    "fundamentals": ["security_id", "fiscal_period", "statement_type", "line_item", "source_id"],
    "insider_tx": ["security_id", "filer_cik", "issuer_cik", "transaction_code", "effective_date", "source_id"],
    "earnings_calendar": ["security_id", "report_date", "source_id"],
    "news_articles": ["article_id", "source_id"],
    "social_posts": ["post_id_hash", "source_id"],
    "entity_mentions": ["mention_id"],
    "sentiment_annotations": ["annotation_id"],
    "attention_metrics": ["security_id", "window_start", "window_end", "window_type"],
    "corp_actions": ["security_id", "action_type", "effective_date", "source_id"],
}


def write_dataset(con: duckdb.DuckDBPyConnection, table: str, df: pl.DataFrame) -> int:
    """Generic canonical write for any dataset table using MERGE INTO."""
    df = compute_version_hash(df)
    natural_keys = _DATASET_KEYS.get(table, ["id"])
    return _merge_into(con, table, natural_keys + ["available_at", "version_hash"], df)


def _merge_into(
    con: duckdb.DuckDBPyConnection,
    table: str,
    dedup_keys: list[str],
    df: pl.DataFrame,
) -> int:
    """Upsert data using MERGE INTO. Dedups on (dedup_keys)."""
    cols = ", ".join(df.columns)

    con.execute("DROP TABLE IF EXISTS _staging")
    polars_to_duckdb(con, df, "_staging")

    col_defs = ", ".join(f'"{c}" VARCHAR' for c in df.columns)
    con.execute(f"CREATE TABLE IF NOT EXISTS {table} ({col_defs})")

    join_on = " AND ".join(f"target.{k} = source.{k}" for k in dedup_keys)
    con.execute(f"""
        MERGE INTO {table} target
        USING (SELECT {cols} FROM _staging) source
        ON ({join_on})
        WHEN NOT MATCHED THEN INSERT ({cols}) VALUES ({cols})
    """)

    count = con.execute("SELECT COUNT(*) FROM _staging").fetchone()
    con.execute("DROP TABLE IF EXISTS _staging")
    return count[0] if count else 0
