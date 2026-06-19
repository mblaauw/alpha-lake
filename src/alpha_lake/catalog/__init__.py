from __future__ import annotations

import pathlib

import duckdb

from alpha_lake.config import RootConfig
from alpha_lake.duckdb_ext import configure_s3, ensure_extensions

_SCHEMA_SQL = pathlib.Path(__file__).parent / "schema.sql"


def _build_connect_path(cfg: RootConfig) -> str:
    raw = cfg.lake.catalog
    if raw.startswith("ducklake:postgres:"):
        conn_str = raw.removeprefix("ducklake:postgres:")
        return f"postgres://{conn_str}"
    if raw.startswith("ducklake:sqlite:"):
        return raw.removeprefix("ducklake:sqlite:")
    return raw


def connect(cfg: RootConfig) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("SET timezone = 'UTC'")

    if cfg.lake.runtime == "stack":
        ensure_extensions(con)
        configure_s3(
            con,
            endpoint=cfg.s3.endpoint,
            use_ssl=cfg.s3.use_ssl,
            url_style=cfg.s3.url_style,
        )
        con.execute(f"CALL postgres_attach('{_build_connect_path(cfg)}')")
    else:
        db_path = _build_connect_path(cfg)
        con.execute(f"ATTACH '{db_path}' AS lake_catalog (TYPE sqlite)")

    return con


def bootstrap(cfg: RootConfig) -> None:
    con = connect(cfg)
    if _SCHEMA_SQL.exists():
        sql = _SCHEMA_SQL.read_text()
        for statement in sql.split(";"):
            stmt = statement.strip()
            if stmt:
                con.execute(stmt)
    else:
        _create_default_schema(con)
    con.close()


def _create_default_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS source (
            source_id VARCHAR PRIMARY KEY,
            name VARCHAR NOT NULL,
            description VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS source_dataset (
            source_id VARCHAR NOT NULL,
            dataset VARCHAR NOT NULL,
            enabled BOOLEAN DEFAULT TRUE,
            parser_version INT DEFAULT 1,
            PRIMARY KEY (source_id, dataset)
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS ingestion_run (
            run_id VARCHAR PRIMARY KEY,
            source_id VARCHAR NOT NULL,
            dataset VARCHAR NOT NULL,
            status VARCHAR NOT NULL DEFAULT 'pending',
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            rows_ingested INT DEFAULT 0,
            error_count INT DEFAULT 0
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS manifest (
            fetch_id VARCHAR PRIMARY KEY,
            source_id VARCHAR NOT NULL,
            endpoint VARCHAR NOT NULL,
            ingest_ts TIMESTAMP NOT NULL,
            http_status INT,
            content_hash VARCHAR NOT NULL,
            content_type VARCHAR,
            byte_size INT,
            parser_version_intended INT
        )
    """)
