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




def duckdb_to_polars(
    con: duckdb.DuckDBPyConnection,
    query: str,
    params: list | None = None,
) -> pl.DataFrame:
    result = pl.from_arrow(con.execute(query, params or []).to_arrow_table())
    assert isinstance(result, pl.DataFrame)
    return result
