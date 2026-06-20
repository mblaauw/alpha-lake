from __future__ import annotations

import duckdb

from alpha_lake.config import RootConfig


def _build_attach(cfg: RootConfig) -> tuple[str, str]:
    """Build the DuckLake ATTACH parameters from config.

    Returns (attach_string, data_path).
    """
    raw = cfg.lake.catalog
    runtime = cfg.lake.runtime

    if raw.startswith("ducklake:postgres"):
        conn = raw.removeprefix("ducklake:")
        attach = f"ducklake:{conn}"
    elif raw.startswith("ducklake:sqlite:"):
        conn = raw.removeprefix("ducklake:sqlite:")
        attach = f"ducklake:sqlite:{conn}"
    elif runtime == "stack":
        attach = raw
    else:
        attach = f"ducklake:sqlite:{raw}"

    data_path = cfg.lake.data_path
    return attach, data_path


def connect(cfg: RootConfig) -> duckdb.DuckDBPyConnection:
    """Create a DuckDB connection attached to a DuckLake.

    In stack mode: DuckLake + PostgreSQL catalog + S3/RustFS data.
    In embedded mode: DuckLake + SQLite catalog + local FS data.
    """
    con = duckdb.connect()
    con.execute("SET timezone = 'UTC'")

    con.execute("INSTALL ducklake")
    con.execute("LOAD ducklake")

    if cfg.lake.runtime == "stack":
        con.execute("INSTALL postgres")
        con.execute("LOAD postgres")

    attach_str, data_path = _build_attach(cfg)
    con.execute(f"ATTACH '{attach_str}' AS lake_catalog (DATA_PATH '{data_path}')")
    con.execute("USE lake_catalog")
    return con


def bootstrap(cfg: RootConfig) -> None:
    """Initialize the DuckLake catalog.

    DuckLake creates the catalog database and metadata tables automatically
    on ATTACH. No additional DDL is needed for the lake infrastructure.
    """
    con = connect(cfg)
    con.close()


def list_datasets(con: duckdb.DuckDBPyConnection) -> list[dict[str, object]]:
    """List all tables in the DuckLake catalog."""
    rows = con.execute("SHOW TABLES").fetchall()
    skip = {"pg_", "_staging", "staging_bars", "staging_ca", "sqlite_"}
    result = []
    for row in rows:
        table = row[0]
        if any(table.startswith(p) for p in skip):
            continue
        try:
            ver = con.execute(f'SELECT MAX(schema_version) FROM "{table}"').fetchone()
            version = ver[0] if ver and ver[0] else 0
            count = con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()
            row_count = count[0] if count and count[0] else 0
        except Exception:
            version = 0
            row_count = 0
        result.append({"dataset": table, "schema_version": version, "rows": row_count})
    return result


def dataset_health(con: duckdb.DuckDBPyConnection, dataset: str) -> dict:
    """Return health metrics for a single dataset."""
    info: dict = {"dataset": dataset, "status": "unknown", "rows": 0, "latest_date": None}
    try:
        cnt = con.execute(f"SELECT COUNT(*) FROM {dataset}").fetchone()
        info["rows"] = cnt[0] if cnt else 0
    except Exception:
        info["status"] = "error"
        return info
    try:
        col = "effective_date"
        latest = con.execute(f"SELECT MAX({col}) FROM {dataset}").fetchone()
        info["latest_date"] = str(latest[0]) if latest and latest[0] else None
    except Exception:
        pass
    info["status"] = "ok" if info["rows"] > 0 else "empty"
    return info


def catalog_health(con: duckdb.DuckDBPyConnection) -> dict:
    """Return overall catalog health metrics including snapshot and metadata info."""
    result: dict = {"snapshots": 0, "latest_snapshot_id": None}
    try:
        r = con.execute(
            "SELECT snapshot_id FROM ducklake_last_committed_snapshot('lake_catalog')"
        ).fetchone()
        result["latest_snapshot_id"] = r[0] if r else None
    except Exception:
        pass
    try:
        r = con.execute("SELECT COUNT(*) FROM ducklake_snapshots('lake_catalog')").fetchone()
        result["snapshots"] = r[0] if r else 0
    except Exception:
        pass
    return result


def list_snapshots(con: duckdb.DuckDBPyConnection) -> list[dict]:
    """List all DuckLake snapshots with details."""
    rows = con.execute(
        "SELECT snapshot_id, snapshot_time, changes FROM ducklake_snapshots('lake_catalog')"
    ).fetchall()
    return [{"snapshot_id": r[0], "timestamp": str(r[1]), "changes": str(r[2])} for r in rows]


def set_snapshot(con: duckdb.DuckDBPyConnection, snapshot_id: str) -> None:
    """Pin reads to a specific DuckLake snapshot for reproducibility.

    Attempts to use DuckLake's snapshot pinning API when available.
    Raises NotImplementedError if the DuckLake version doesn't support it.
    """
    catalog = "lake_catalog"
    try:
        con.execute(
            f"SELECT * FROM ducklake_set_option('{catalog}', 'snapshot_id', ?)",
            [snapshot_id],
        )
    except Exception as e:
        raise NotImplementedError(
            f"Snapshot pinning not supported by this DuckLake version: {e}"
        ) from e


def resolve_ingestion_run(con: duckdb.DuckDBPyConnection, run_id: str) -> int | None:
    """Map an ingestion_run_id to its DuckLake snapshot ID.

    Returns the snapshot_id or None if not found.
    """
    catalog = "lake_catalog"
    run_id_ts = run_id.removeprefix("run_").split("_")[0]
    row = con.execute(
        f"""
        SELECT snapshot_id FROM ducklake_snapshots('{catalog}')
        WHERE changes::VARCHAR LIKE '%' || ? || '%'
        ORDER BY snapshot_id DESC
        LIMIT 1
        """,
        [run_id_ts],
    ).fetchone()
    return row[0] if row else None
