import duckdb
import polars as pl

from alpha_lake.interop import duckdb_to_polars, polars_to_duckdb


def test_polars_to_duckdb_roundtrip():
    con = duckdb.connect()
    df = pl.DataFrame({"x": [1, 2, 3], "y": ["a", "b", "c"]})
    polars_to_duckdb(con, df, "test_t")
    result = con.execute("SELECT * FROM test_t ORDER BY x").fetchall()
    assert result == [(1, "a"), (2, "b"), (3, "c")]
    con.close()


def test_duckdb_to_polars():
    con = duckdb.connect()
    con.execute("CREATE TABLE nums AS SELECT * FROM (VALUES (1), (2), (3)) t(n)")
    result = duckdb_to_polars(con, "SELECT * FROM nums WHERE n > 1")
    assert result.shape == (2, 1)
    assert result["n"].to_list() == [2, 3]
    con.close()


def test_lazyframe_supported():
    con = duckdb.connect()
    lf = pl.LazyFrame({"a": [10, 20]})
    polars_to_duckdb(con, lf, "lazy_t")
    _r = con.execute("SELECT SUM(a) FROM lazy_t").fetchone()
    assert _r is not None
    result = _r[0]
    assert result == 30
    con.close()
