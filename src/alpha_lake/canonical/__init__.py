from __future__ import annotations

import hashlib
import json

import duckdb
import polars as pl

from alpha_lake.interop import polars_to_duckdb

NORMALIZATION_VERSION: int = 1
"""Bump when the canonical serialization recipe changes.

Every bump invalidates all prior golden replay fixtures.
"""


def compute_version_hash(df: pl.DataFrame) -> pl.DataFrame:
    """Compute semantic version_hash per row.

    Recipe (pinned at normalization_version=1):
    1. Sort column keys alphabetically (exclude version_hash itself).
    2. Serialize with `json.dumps(sort_keys=True, default=str, separators=(",",":"))`.
    3. Pinned float precision via `round(val, 10)`.
    4. Dates serialized as ISO strings via `default=str`.
    5. Stable null representation: Python `None` → JSON `null`.
    6. SHA-256 of the canonical JSON bytes.
    """
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
        raw = json.dumps(
            canonical,
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        )
        row_hashes.append(hashlib.sha256(raw.encode()).hexdigest())
    return df.with_columns(
        pl.Series("version_hash", row_hashes),
        pl.lit(NORMALIZATION_VERSION).alias("normalization_version"),
    )


_COLUMNS = [
    "security_id", "effective_date", "available_at", "source_id",
    "open", "high", "low", "close", "volume",
    "source_fetch_id", "raw_payload_hash", "ingestion_run_id",
    "content_hash", "version_hash",
    "schema_version", "parser_version", "quality_status",
    "source_published_at", "ingested_at", "validated_at",
    "normalization_version",
]
"""Column order for lake_bars INSERT. Must match Polars output order."""


def write_bars(con: duckdb.DuckDBPyConnection, df: pl.DataFrame) -> int:
    df = compute_version_hash(df)

    con.execute(f"""
        CREATE TABLE IF NOT EXISTS lake_bars (
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
            normalization_version INT DEFAULT {NORMALIZATION_VERSION},
            schema_version INT DEFAULT 1,
            parser_version INT DEFAULT 1,
            quality_status VARCHAR DEFAULT 'valid'
        )
    """)

    polars_to_duckdb(con, df, "staging_bars")

    cols = ", ".join(_COLUMNS)
    con.execute(f"""
        INSERT INTO lake_bars ({cols})
        SELECT {cols}
        FROM staging_bars s
        WHERE NOT EXISTS (
            SELECT 1 FROM lake_bars t
            WHERE t.security_id = s.security_id
              AND t.effective_date = s.effective_date
              AND t.source_id = s.source_id
              AND t.available_at = s.available_at
              AND t.version_hash = s.version_hash
        )
    """)

    count = con.execute("SELECT COUNT(*) FROM staging_bars").fetchone()[0]
    con.execute("DROP TABLE IF EXISTS staging_bars")
    return count


def write_corp_actions(con: duckdb.DuckDBPyConnection, df: pl.DataFrame) -> int:
    df = compute_version_hash(df)

    con.execute("""
        CREATE TABLE IF NOT EXISTS corp_actions (
            id VARCHAR,
            security_id VARCHAR NOT NULL,
            effective_date DATE NOT NULL,
            available_at TIMESTAMPTZ NOT NULL,
            source_id VARCHAR NOT NULL,
            action_type VARCHAR NOT NULL,
            ratio_numerator DOUBLE,
            ratio_denominator DOUBLE,
            dividend_amount DOUBLE,
            dividend_currency VARCHAR,
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

    con.execute("DROP TABLE IF EXISTS staging_ca")
    polars_to_duckdb(con, df, "staging_ca")

    ca_cols = "security_id, effective_date, available_at, source_id, action_type, ratio_numerator, ratio_denominator, dividend_amount, dividend_currency, source_fetch_id, raw_payload_hash, ingestion_run_id, content_hash, version_hash, schema_version, parser_version, quality_status"
    con.execute(f"""
        INSERT INTO corp_actions
        SELECT
            sha256(concat_ws('|', security_id, action_type, effective_date, source_id, version_hash)) AS id,
            {ca_cols}
        FROM staging_ca s
        WHERE NOT EXISTS (
            SELECT 1 FROM corp_actions t
            WHERE t.security_id = s.security_id
              AND t.action_type = s.action_type
              AND t.effective_date = s.effective_date
              AND t.source_id = s.source_id
              AND t.available_at = s.available_at
              AND t.version_hash = s.version_hash
        )
    """)

    count = con.execute("SELECT COUNT(*) FROM staging_ca").fetchone()[0]
    con.execute("DROP TABLE IF EXISTS staging_ca")
    return count


_DATASET_KEYS: dict[str, list[str]] = {
    "fundamentals": ["security_id", "fiscal_period", "statement_type", "line_item", "source_id"],
    "insider_tx": ["security_id", "filer_cik", "issuer_cik", "transaction_code", "effective_date", "source_id"],
    "earnings_calendar": ["security_id", "report_date", "source_id"],
    "news_articles": ["article_id", "source_id"],
    "social_posts": ["post_id_hash", "source_id"],
    "entity_mentions": ["mention_id"],
    "sentiment_annotations": ["annotation_id"],
    "attention_metrics": ["security_id", "window_start", "window_end", "window_type"],
}


def write_dataset(con: duckdb.DuckDBPyConnection, table: str, df: pl.DataFrame) -> int:
    """Generic canonical write for any dataset table.

    Creates table if not exists, computes version_hash, dedup by natural key.
    """
    df = compute_version_hash(df)

    cols = ", ".join(df.columns)
    placeholders = ", ".join(f"s.{c}" for c in df.columns)
    natural_keys = _DATASET_KEYS.get(table, ["id"])

    df_no_nv = df.drop("normalization_version")
    staging_cols = ", ".join(df_no_nv.columns)
    staging_placeholders = ", ".join(f"s.{c}" for c in df_no_nv.columns)

    con.execute("DROP TABLE IF EXISTS _staging")
    polars_to_duckdb(con, df_no_nv, "_staging")

    join_on = " AND ".join(f"t.{k} = s.{k}" for k in natural_keys)
    con.execute(f"""
        INSERT INTO {table} ({staging_cols})
        SELECT {staging_placeholders}
        FROM _staging s
        WHERE NOT EXISTS (
            SELECT 1 FROM {table} t
            WHERE {join_on}
              AND t.available_at = s.available_at
              AND t.version_hash = s.version_hash
        )
    """)

    count = con.execute("SELECT COUNT(*) FROM _staging").fetchone()[0]
    con.execute("DROP TABLE IF EXISTS _staging")
    return count
