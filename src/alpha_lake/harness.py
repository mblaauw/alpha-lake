from __future__ import annotations

import os
import tempfile
from pathlib import Path

import duckdb


class EmbeddedHarness:
    """SQLite/local-fs embedded harness for tests and replay.

    Replaces Postgres → SQLite/DuckDB, RustFS → local filesystem,
    OTel gRPC → console. Same code paths via dependency injection.
    """

    def __init__(self, db_path: str | None = None):
        self._conn: duckdb.DuckDBPyConnection | None = None
        self._tmpdir: tempfile.TemporaryDirectory | None = None
        self._db_path = db_path

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            raise RuntimeError("harness not started — call .start()")
        return self._conn

    @property
    def data_path(self) -> Path:
        if self._tmpdir is None:
            raise RuntimeError("harness not started — call .start()")
        return Path(self._tmpdir.name)

    def start(self) -> None:
        os.environ["ALPHA_LAKE_CONFIG"] = ""
        self._tmpdir = tempfile.TemporaryDirectory(prefix="alpha_lake_test_")
        data_dir = Path(self._tmpdir.name)
        (data_dir / "raw").mkdir(parents=True, exist_ok=True)

        self._conn = duckdb.connect(self._db_path or ":memory:")
        self._conn.execute("SET timezone = 'UTC'")
        self._conn.execute("INSTALL ducklake")
        self._conn.execute("LOAD ducklake")
        self._conn.execute("CREATE SCHEMA IF NOT EXISTS lake_catalog")
        self._conn.execute("USE lake_catalog")

    def stop(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
        if self._tmpdir:
            self._tmpdir.cleanup()
            self._tmpdir = None
