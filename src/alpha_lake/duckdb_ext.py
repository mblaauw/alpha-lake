from __future__ import annotations

import duckdb

_STANDARD_EXTENSIONS = [
    "httpfs",
    "parquet",
    "postgres",
]


def ensure_extensions(con: duckdb.DuckDBPyConnection) -> None:
    for ext in _STANDARD_EXTENSIONS:
        try:
            con.execute(f"LOAD {ext}")
        except Exception:
            con.execute(f"INSTALL {ext}")
            con.execute(f"LOAD {ext}")


def configure_s3(
    con: duckdb.DuckDBPyConnection,
    endpoint: str,
    region: str = "us-east-1",
    use_ssl: bool = False,
    url_style: str = "path",
) -> None:
    ensure_extensions(con)
    con.execute("SET s3_region = ?", [region])
    con.execute("SET s3_url_style = ?", [url_style])
    con.execute("SET s3_endpoint = ?", [endpoint])
    con.execute("SET s3_use_ssl = ?", [use_ssl])
