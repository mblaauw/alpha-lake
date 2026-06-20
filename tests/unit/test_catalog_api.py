import duckdb

from alpha_lake.catalog import dataset_health, list_datasets


def test_list_datasets():
    con = duckdb.connect()
    con.execute("INSTALL ducklake")
    con.execute("LOAD ducklake")
    con.execute("CREATE TABLE IF NOT EXISTS lake_bars (security_id VARCHAR)")
    datasets = list_datasets(con)
    names = [d["dataset"] for d in datasets]
    assert "lake_bars" in names
    con.close()


def test_dataset_health():
    con = duckdb.connect()
    con.execute("INSTALL ducklake")
    con.execute("LOAD ducklake")
    con.execute("CREATE TABLE IF NOT EXISTS lake_bars (security_id VARCHAR)")
    h = dataset_health(con, "lake_bars")
    assert h["status"] == "empty"
    assert h["rows"] == 0
    con.close()
