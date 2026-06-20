from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import duckdb
import polars as pl

from alpha_lake.canonical import write_bars, write_dataset
from alpha_lake.catalog import bootstrap, connect
from alpha_lake.config import get_config
from alpha_lake.interop import polars_to_duckdb
from alpha_lake.normalize import bars_from_json
from alpha_lake.quality import check_market_sanity
from alpha_lake.raw import archive
from alpha_lake.source_registry import get_primary_source


def ingest_bars(
    con: duckdb.DuckDBPyConnection,
    security_ids: list[str],
    from_date: str = "",
    to_date: str = "",
    source_id: str | None = None,
) -> int:
    """Run the full bars ingestion pipeline for a list of security IDs.

    NOTE: Currently uses synthetic sample data. Real API fetch will be
    wired in a future update when connector API keys are available in CI.

    1. Generate synthetic raw data
    2. Archive raw bytes
    3. Normalize to Polars DataFrame
    4. Validate with market sanity checks
    5. Write to canonical table
    """
    src = source_id or get_primary_source("bars_daily")
    if not src:
        raise ValueError("No source configured for bars_daily")

    run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    total = 0

    for sid in security_ids:
        manifest_data = {
            "source_id": src,
            "endpoint": f"/eod/{sid}",
            "content_hash": "",
            "byte_size": 0,
            "http_status": 0,
            "parser_version_intended": 1,
        }
        ingest_ts = datetime.now(timezone.utc).isoformat()
        raw_content = f'{{"date":"{from_date or to_date or date.today().isoformat()}","open":100,"high":101,"low":99,"close":100.5,"volume":10000}}'
        raw_bytes = raw_content.encode()

        content_hash = archive(raw_bytes)

        df = bars_from_json(
            raw=[{"date": from_date or date.today().isoformat(),
                   "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 10000}],
            security_id=sid,
            source_id=src,
            source_fetch_id=f"fetch_{sid}",
            ingestion_run_id=run_id,
            content_hash=content_hash,
            available_at=datetime.now(timezone.utc),
            ingested_at=datetime.now(timezone.utc),
        )

        df = check_market_sanity(df)
        total += write_bars(con, df)

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
    """Reparse raw archive data and rewrite canonical rows."""
    from alpha_lake.raw import read_raw
    from alpha_lake.normalize import bars_from_json
    from alpha_lake.quality import check_market_sanity
    import json
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
            df = bars_from_json(raw_data, sid, src_id, fetch_id, run_id, content_hash, avail_at, ingested_at)
            df = check_market_sanity(df)
            total += write_bars(con, df)
    return total


def compact_dataset(con: duckdb.DuckDBPyConnection, table: str) -> int:
    """Compact a canonical table by removing duplicate versions.

    Keeps only the newest available_at per (natural_key + version_hash).
    """
    key_map = {
        "lake_bars": ["security_id", "effective_date", "source_id"],
        "fundamentals": ["security_id", "fiscal_period", "statement_type", "line_item", "source_id"],
        "corp_actions": ["security_id", "action_type", "effective_date", "source_id"],
    }
    keys = key_map.get(table)
    if not keys:
        raise ValueError(f"No key map for {table}")

    key_cols = ", ".join(keys)
    # Note: rowid works in DuckDB/SQLite but NOT in Postgres through postgres_scan.
    con.execute(f"""
        DELETE FROM {table}
        WHERE rowid NOT IN (
            SELECT MIN(rowid) FROM {table}
            GROUP BY {key_cols}, available_at, version_hash
        )
    """)
    _r = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    return _r[0] if _r else 0
