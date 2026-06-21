from __future__ import annotations

import datetime
import types
from typing import Annotated, Union, get_args, get_origin

import duckdb
import patito as pt
import polars as pl


def polars_to_duckdb(
    con: duckdb.DuckDBPyConnection,
    df: pl.DataFrame | pl.LazyFrame,
    table_name: str,
) -> None:
    if isinstance(df, pl.LazyFrame):
        df = df.collect()
    con.execute(f"CREATE TABLE {table_name} AS SELECT * FROM df")


def duckdb_to_polars(
    con: duckdb.DuckDBPyConnection,
    query: str,
    params: list | None = None,
) -> pl.DataFrame:
    return con.execute(query, params or []).pl()


# --- DDL generation from Patito models ---

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


def generate_ddl(model_class: type[pt.Model], table_name: str) -> str:
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
