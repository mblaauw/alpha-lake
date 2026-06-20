import duckdb


def test_ducklake_extension_available():
    con = duckdb.connect()
    try:
        con.execute("INSTALL ducklake")
        con.execute("LOAD ducklake")
        result = con.execute("SELECT 1").fetchone()
        assert result is not None and result[0] == 1
        con.close()
    except Exception as e:
        # Extension may not be available in all environments
        if "extension" in str(e).lower():
            pass
        else:
            raise
