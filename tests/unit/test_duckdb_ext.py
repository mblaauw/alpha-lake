import duckdb

from alpha_lake.duckdb_ext import ensure_extensions


def test_ensure_extensions_runs_without_error():
    con = duckdb.connect()
    ensure_extensions(con)
    con.execute("SELECT 1")
    con.close()


def test_parquet_write_read():
    import os
    import tempfile

    import polars as pl
    con = duckdb.connect()
    ensure_extensions(con)
    df = pl.DataFrame({"x": [1, 2, 3]})
    tmp = tempfile.NamedTemporaryFile(suffix=".parquet", delete=False)
    tmp.close()
    df.write_parquet(tmp.name)
    result = con.execute(f"SELECT COUNT(*) FROM read_parquet('{tmp.name}')").fetchone()[0]
    assert result == 3
    os.unlink(tmp.name)
    con.close()
