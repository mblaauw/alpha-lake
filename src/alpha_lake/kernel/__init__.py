from __future__ import annotations

import pathlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb

_SQL_DIR = pathlib.Path(__file__).parent / "sql"

# Cache SQL file contents at import time so register_kernel doesn't
# read from disk on every call (issue #365).
_SQL_FILES: list[str] = [p.read_text() for p in sorted(_SQL_DIR.glob("*.sql"))]


def register_kernel(con: duckdb.DuckDBPyConnection) -> None:
    from alpha_lake.source_registry import get_source_precedence

    con.execute(
        "CREATE TABLE IF NOT EXISTS _kernel_source_priority ("
        "dataset VARCHAR, source_id VARCHAR, priority INT)"
    )
    con.execute("DELETE FROM _kernel_source_priority")
    rows: list[tuple[str, str, int]] = []
    precedence_datasets: set[str] = {"bars_daily"}
    try:
        from alpha_lake.config import get_config as _get_cfg

        cfg = _get_cfg()
        precedence_datasets.update(cfg.precedence.keys())
    except AssertionError:
        pass
    for dataset in sorted(precedence_datasets):
        sources = get_source_precedence(dataset)
        for i, source_id in enumerate(sources):
            rows.append((dataset, source_id, i))
    if rows:
        con.executemany(
            "INSERT INTO _kernel_source_priority (dataset, source_id, priority) VALUES (?, ?, ?)",
            rows,
        )

    # Ensure referenced tables exist so SQL macros compile at parse time.
    # In production the DuckLake catalog provides them; in tests we create
    # minimal stubs that writes replace with the proper schema later.
    # DDL is derived from the Patito model to keep BarFact as the single
    # schema authority (see epic-308 / issue #364).
    from alpha_lake.interop import generate_ddl
    from alpha_lake.models.bar_fact import BarFact

    con.execute(generate_ddl(BarFact, "lake_bars"))
    con.execute(
        "CREATE OR REPLACE TEMPORARY VIEW _spine AS "
        "SELECT CAST(NULL AS VARCHAR) AS security_id, "
        "CAST(NULL AS DATE) AS effective_date, "
        "CAST(NULL AS TIMESTAMPTZ) AS as_of WHERE 1=0"
    )

    for sql in _SQL_FILES:
        con.execute(sql)
