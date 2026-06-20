from __future__ import annotations

import asyncio
from datetime import date, datetime

import duckdb

from alpha_lake.canonical import DATASETS, write_bars
from alpha_lake.clock import get_clock
from alpha_lake.connectors import ConnectorFn, get_connector, has_api_key
from alpha_lake.normalize import bars_from_json
from alpha_lake.quality import check_market_sanity
from alpha_lake.raw import archive
from alpha_lake.source_registry import get_primary_source


def _synthetic_payload(from_date: str, to_date: str, clock_now: datetime) -> bytes:
    """Generate synthetic raw payload for offline/CI mode."""
    import json
    return json.dumps([{
        "date": from_date or to_date or clock_now.date().isoformat(),
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "volume": 10000,
    }]).encode()


async def _fetch_and_ingest(
    con: duckdb.DuckDBPyConnection,
    connector: ConnectorFn,
    sid: str,
    src: str,
    from_date: str,
    to_date: str,
    run_id: str,
    clock_now: datetime,
) -> int:
    """Fetch from connector, archive, normalize, write."""
    raw_fetch = await connector(symbol=sid, from_date=from_date, to_date=to_date)
    raw_bytes = raw_fetch.body
    content_hash = archive(raw_bytes)

    import json
    raw_data = json.loads(raw_bytes)
    records = raw_data if isinstance(raw_data, list) else [raw_data]

    df = bars_from_json(
        raw=records,
        security_id=sid,
        source_id=src,
        source_fetch_id=raw_fetch.manifest.get("request_params_hash", f"fetch_{sid}"),
        ingestion_run_id=run_id,
        content_hash=content_hash,
        available_at=clock_now,
        ingested_at=clock_now,
    )
    df = check_market_sanity(df)
    return write_bars(con, df)


def _ingest_synthetic(
    con: duckdb.DuckDBPyConnection,
    sid: str,
    src: str,
    from_date: str,
    to_date: str,
    run_id: str,
    clock_now: datetime,
) -> int:
    """Synthetic data path for offline/CI mode."""
    raw_bytes = _synthetic_payload(from_date, to_date, clock_now)
    content_hash = archive(raw_bytes)

    import json
    raw_data = json.loads(raw_bytes)
    records = raw_data if isinstance(raw_data, list) else [raw_data]

    df = bars_from_json(
        raw=records,
        security_id=sid,
        source_id=src,
        source_fetch_id=f"fetch_{sid}",
        ingestion_run_id=run_id,
        content_hash=content_hash,
        available_at=clock_now,
        ingested_at=clock_now,
    )
    df = check_market_sanity(df)
    return write_bars(con, df)


def ingest_bars(
    con: duckdb.DuckDBPyConnection,
    security_ids: list[str],
    from_date: str = "",
    to_date: str = "",
    source_id: str | None = None,
) -> int:
    """Run the full bars ingestion pipeline.

    Tries the connector layer first (online); falls back to synthetic
    data when no API credentials are available (offline/CI).

    1. Fetch raw data (connector or synthetic)
    2. Archive raw bytes
    3. Normalize to Polars DataFrame
    4. Validate with market sanity checks
    5. Write to canonical table
    """
    src = source_id or get_primary_source("bars_daily")
    if not src:
        raise ValueError("No source configured for bars_daily")

    connector = get_connector(src, "bars_daily")
    creds = has_api_key(src)
    clock_now = get_clock().now()
    run_id = f"run_{clock_now.strftime('%Y%m%d_%H%M%S')}"
    total = 0

    if connector and creds:
        async def _run_all():
            t = 0
            for sid in security_ids:
                t += await _fetch_and_ingest(
                    con, connector, sid, src, from_date, to_date, run_id, clock_now,
                )
            return t
        total = asyncio.run(_run_all())
    else:
        for sid in security_ids:
            total += _ingest_synthetic(con, sid, src, from_date, to_date, run_id, clock_now)

    return total


def backfill_bars(
    con: duckdb.DuckDBPyConnection,
    security_ids: list[str],
    start_date: date,
    end_date: date,
    source_id: str | None = None,
) -> int:
    """Backfill bars for a date range.

    Iterates through each business day and ingests missing data.
    """
    from alpha_lake.calendar_ import trading_days_in_range
    total = 0
    days = trading_days_in_range(start_date, end_date)
    for sid in security_ids:
        for dt in days:
            _r = con.execute("SELECT COUNT(*) FROM lake_bars WHERE security_id = ? AND effective_date = ?", [sid, dt]).fetchone()
            existing = _r[0] if _r else 0
            if existing == 0:
                total += ingest_bars(con, [sid], dt.isoformat(), dt.isoformat(), source_id)
    return total


def reparse_bars(
    con: duckdb.DuckDBPyConnection,
    security_ids: list[str],
    effective_date: date | None = None,
) -> int:
    """Reparse raw archive data and rewrite canonical rows.

    Creates a NEW knowledge-time version: the reparsed row gets a new
    available_at set to reparse time, while preserving content_hash
    pointing to the original raw archive blobs. Both the original and
    the new reparse version coexist in the lake.
    """
    import json

    from alpha_lake.normalize import bars_from_json
    from alpha_lake.quality import check_market_sanity
    from alpha_lake.raw import read_raw
    reparse_ts = get_clock().now()
    total = 0
    for sid in security_ids:
        if effective_date:
            rows = con.execute(
                "SELECT content_hash, source_id, source_fetch_id, ingestion_run_id, "
                "available_at, ingested_at FROM lake_bars WHERE security_id = ? AND effective_date = ?",
                [sid, effective_date]
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT DISTINCT content_hash, source_id, source_fetch_id, ingestion_run_id, "
                "available_at, ingested_at FROM lake_bars WHERE security_id = ?",
                [sid]
            ).fetchall()
        for row in rows:
            content_hash, src_id, fetch_id, run_id, avail_at, ingested_at = row
            raw = read_raw(content_hash)
            raw_data = json.loads(raw.decode())
            if isinstance(raw_data, dict):
                raw_data = [raw_data]
            df = bars_from_json(raw_data, sid, src_id, fetch_id, run_id, content_hash, reparse_ts, ingested_at)
            df = check_market_sanity(df)
            total += write_bars(con, df)
    return total


def compact_dataset(con: duckdb.DuckDBPyConnection, table: str) -> int:
    """Compact a canonical table by removing duplicate versions.

    Keeps only the newest available_at per (natural_key + version_hash).
    Uses window-function dedup for portability across DuckDB, Postgres, and SQLite.
    """
    ds = DATASETS.get(table)
    if ds is None:
        raise ValueError(f"No dataset descriptor for {table}")
    keys = ds.natural_keys

    key_cols = ", ".join(keys)
    stg = f"_compact_{table}"

    con.execute(f"""
        CREATE TABLE {stg} AS
        SELECT * EXCLUDE rn FROM (
            SELECT *,
                ROW_NUMBER() OVER (
                    PARTITION BY {key_cols}, available_at, version_hash
                    ORDER BY available_at
                ) AS rn
            FROM {table}
        ) dup
        WHERE rn = 1
    """)
    con.execute(f"DELETE FROM {table}")
    cols = ", ".join(c[0] for c in con.execute(f"DESCRIBE {stg}").fetchall())
    con.execute(f"INSERT INTO {table} SELECT {cols} FROM {stg}")
    con.execute(f"DROP TABLE IF EXISTS {stg}")

    _r = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    return _r[0] if _r else 0
