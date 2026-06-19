from __future__ import annotations

import duckdb
import polars as pl


def polars_to_duckdb(
    con: duckdb.DuckDBPyConnection,
    df: pl.DataFrame | pl.LazyFrame,
    table_name: str,
) -> None:
    if isinstance(df, pl.LazyFrame):
        df = df.collect()
    rel = con.from_arrow(df.to_arrow())
    rel.create(table_name)


def register_view(
    con: duckdb.DuckDBPyConnection,
    df: pl.DataFrame | pl.LazyFrame,
    view_name: str,
) -> None:
    if isinstance(df, pl.LazyFrame):
        df = df.collect()
    con.register(view_name, df.to_arrow())


def duckdb_to_polars(
    con: duckdb.DuckDBPyConnection,
    query: str,
    params: list | None = None,
) -> pl.DataFrame:
    return pl.from_arrow(con.execute(query, params or []).to_arrow_table())
