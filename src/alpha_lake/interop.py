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
    con.execute(f"CREATE TABLE {table_name} AS SELECT * FROM df")


def duckdb_to_polars(
    con: duckdb.DuckDBPyConnection,
    query: str,
    params: list | None = None,
) -> pl.DataFrame:
    return con.execute(query, params or []).pl()
