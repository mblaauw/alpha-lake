import duckdb


def test_ducklake_extension_available():
    duckdb.connect(":memory:").execute("SELECT 1").fetchone()
