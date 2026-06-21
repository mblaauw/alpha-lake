from __future__ import annotations

import pathlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb

_SQL_DIR = pathlib.Path(__file__).parent / "sql"


def register_kernel(con: duckdb.DuckDBPyConnection) -> None:
    from alpha_lake.source_registry import _SOURCE_PRECEDENCE

    con.execute(
        "CREATE TABLE IF NOT EXISTS _kernel_source_priority ("
        "dataset VARCHAR, source_id VARCHAR, priority INT)"
    )
    con.execute("DELETE FROM _kernel_source_priority")
    for dataset, sources in _SOURCE_PRECEDENCE.items():
        for i, source_id in enumerate(sources):
            con.execute(
                "INSERT INTO _kernel_source_priority VALUES (?, ?, ?)",
                [dataset, source_id, i],
            )

    # Ensure referenced tables exist so SQL macros compile at parse time.
    # In production the DuckLake catalog provides them; in tests we create
    # minimal stubs that writes replace with the proper schema later.
    con.execute("""
        CREATE TABLE IF NOT EXISTS lake_bars (
            security_id VARCHAR,
            effective_date DATE,
            available_at TIMESTAMPTZ,
            source_id VARCHAR,
            open DOUBLE,
            high DOUBLE,
            low DOUBLE,
            close DOUBLE,
            volume BIGINT,
            source_fetch_id VARCHAR,
            raw_payload_hash VARCHAR,
            ingestion_run_id VARCHAR,
            content_hash VARCHAR,
            version_hash VARCHAR,
            schema_version INTEGER,
            parser_version INTEGER,
            normalization_version INTEGER DEFAULT 1,
            quality_status VARCHAR,
            source_published_at TIMESTAMPTZ,
            ingested_at TIMESTAMPTZ,
            validated_at TIMESTAMPTZ
        )
    """)
    con.execute(
        "CREATE OR REPLACE TEMPORARY VIEW _spine AS "
        "SELECT CAST(NULL AS VARCHAR) AS security_id, "
        "CAST(NULL AS DATE) AS effective_date, "
        "CAST(NULL AS TIMESTAMPTZ) AS as_of WHERE 1=0"
    )

    for path in sorted(_SQL_DIR.glob("*.sql")):
        con.execute(path.read_text())
