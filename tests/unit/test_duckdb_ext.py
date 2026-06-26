import duckdb
import pytest


def test_ducklake_extension_available():
    duckdb.connect(":memory:").execute("SELECT 1").fetchone()
