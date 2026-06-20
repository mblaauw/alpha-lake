from __future__ import annotations

import datetime
import hashlib
import json
import types
from typing import Annotated, Union, get_args, get_origin

import duckdb
import patito as pt
import polars as pl

from alpha_lake.interop import polars_to_duckdb
from alpha_lake.models.bar_fact import BarFact
from alpha_lake.models.corp_action_fact import CorpActionFact
from alpha_lake.models.dataset_models import (
    AttentionMetricFact,
    EarningsEventFact,
    EntityMentionFact,
    FundamentalFact,
    InsiderTxFact,
    NewsArticleFact,
    SentimentAnnotationFact,
    SocialPostFact,
)

NORMALIZATION_VERSION: int = 1

_TABLE_MODELS: dict[str, type[pt.Model]] = {
    "lake_bars": BarFact,
    "corp_actions": CorpActionFact,
    "fundamentals": FundamentalFact,
    "insider_tx": InsiderTxFact,
    "news_articles": NewsArticleFact,
    "social_posts": SocialPostFact,
    "earnings_calendar": EarningsEventFact,
    "entity_mentions": EntityMentionFact,
    "sentiment_annotations": SentimentAnnotationFact,
    "attention_metrics": AttentionMetricFact,
}

_AUDIT_COLUMNS: list[str] = [
    '"normalization_version" INT DEFAULT 1',
]


def _get_base_type(annotation: object) -> object:
    origin = get_origin(annotation)
    if origin is Annotated:
        return get_args(annotation)[0]
    return annotation


def _is_nullable(annotation: object) -> bool:
    origin = get_origin(annotation)
    if origin is Union or origin is types.UnionType:
        args = get_args(annotation)
        return type(None) in args
    return False


def _type_to_duckdb(annotation: object) -> str:
    base = _get_base_type(annotation)
    origin = get_origin(base)
    if origin is Union or origin is types.UnionType:
        non_none = [a for a in get_args(base) if a is not type(None)]
        if len(non_none) == 1:
            return _type_to_duckdb(non_none[0])
    if base is str:
        return "VARCHAR"
    if base is int:
        return "BIGINT"
    if base is float:
        return "DOUBLE"
    if base is bool:
        return "BOOLEAN"
    if base is datetime.date:
        return "DATE"
    if base is datetime.datetime:
        return "TIMESTAMPTZ"
    return "VARCHAR"


def _format_default(value: object) -> str:
    if isinstance(value, str):
        return f"'{value}'"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, datetime.date):
        return f"'{value.isoformat()}'::DATE"
    if isinstance(value, datetime.datetime):
        return f"'{value.isoformat()}'::TIMESTAMPTZ"
    return str(value)


def _generate_ddl(model_class: type[pt.Model], table_name: str) -> str:
    fields: list[str] = []
    for field_name, field_info in model_class.model_fields.items():
        duckdb_type = _type_to_duckdb(field_info.annotation)
        nullable = _is_nullable(field_info.annotation)
        has_default = not field_info.is_required()
        raw_default = field_info.default

        col_def = f'"{field_name}" {duckdb_type}'
        if not nullable:
            col_def += " NOT NULL"
        if has_default and raw_default is not None:
            col_def += f" DEFAULT {_format_default(raw_default)}"
        fields.append(col_def)

    existing_names = {f.split('"')[1] for f in fields}
    for col in _AUDIT_COLUMNS:
        name = col.split('"')[1]
        if name not in existing_names:
            fields.append(col)

    return f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(fields)})"


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


def write_bars(con: duckdb.DuckDBPyConnection, df: pl.DataFrame) -> int:
    df = compute_version_hash(df)
    con.execute(_generate_ddl(BarFact, "lake_bars"))
    return _merge_into(con, "lake_bars",
        ["security_id", "effective_date", "source_id", "available_at", "version_hash"],
        df)


def write_corp_actions(con: duckdb.DuckDBPyConnection, df: pl.DataFrame) -> int:
    df = compute_version_hash(df)
    con.execute(_generate_ddl(CorpActionFact, "corp_actions"))
    return _merge_into(con, "corp_actions",
        ["security_id", "action_type", "effective_date",
         "source_id", "available_at", "version_hash"],
        df)


_DATASET_KEYS: dict[str, list[str]] = {
    "lake_bars": ["security_id", "effective_date", "source_id"],
    "fundamentals": ["security_id", "fiscal_period", "statement_type", "line_item", "source_id"],
    "insider_tx": ["security_id", "filer_cik", "issuer_cik",
                     "transaction_code", "effective_date", "source_id"],
    "earnings_calendar": ["security_id", "report_date", "source_id"],
    "news_articles": ["article_id", "source_id"],
    "social_posts": ["post_id_hash", "source_id"],
    "entity_mentions": ["mention_id"],
    "sentiment_annotations": ["annotation_id"],
    "attention_metrics": ["security_id", "window_start", "window_end", "window_type"],
    "corp_actions": ["security_id", "action_type", "effective_date", "source_id"],
}


def write_dataset(con: duckdb.DuckDBPyConnection, table: str, df: pl.DataFrame) -> int:
    df = compute_version_hash(df)
    natural_keys = _DATASET_KEYS.get(table, ["id"])
    return _merge_into(con, table, natural_keys + ["available_at", "version_hash"], df)


def _merge_into(
    con: duckdb.DuckDBPyConnection,
    table: str,
    dedup_keys: list[str],
    df: pl.DataFrame,
) -> int:
    cols = ", ".join(df.columns)

    con.execute("DROP TABLE IF EXISTS _staging")
    polars_to_duckdb(con, df, "_staging")

    model = _TABLE_MODELS.get(table)
    if model is not None:
        ddl = _generate_ddl(model, table)
    else:
        col_defs = ", ".join(f'"{c}" VARCHAR' for c in df.columns)
        ddl = f"CREATE TABLE IF NOT EXISTS {table} ({col_defs})"
    con.execute(ddl)

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
