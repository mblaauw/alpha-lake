from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import polars as pl

_BOOTSTRAP_PARQUET = Path("/data/bootstrap/us_daily.parquet")
_STOOQ_SOURCE_ID = "stooq"


def _sanity_check(
    con: duckdb.DuckDBPyConnection,
    bootstrap: pl.DataFrame,
) -> list[str]:
    """Run sanity checks comparing bootstrap data against existing lake bars.

    Returns a list of warning messages (empty = all checks passed).
    """
    warnings: list[str] = []
    reference = ["AAPL", "MSFT", "SPY"]

    for sym in reference:
        stooq = bootstrap.filter(pl.col("security_id") == sym).sort("effective_date")
        if stooq.is_empty():
            warnings.append(f"{sym}: no bootstrap data")
            continue

        # Get last 10 overlapping dates from the lake
        lake_rows = con.execute(
            "SELECT effective_date, close FROM lake_bars"
            " WHERE security_id = ? ORDER BY effective_date DESC LIMIT 10",
            [sym],
        ).fetchall()
        if not lake_rows:
            warnings.append(f"{sym}: no lake data to compare")
            continue

        for ld, lc in lake_rows:
            stooq_row = stooq.filter(pl.col("effective_date") == ld)
            if stooq_row.is_empty():
                warnings.append(f"{sym}: lake date {ld} missing from bootstrap — gap")
                continue
            sc = stooq_row["close"][0]
            if sc == 0:
                continue
            ratio = abs(lc - sc) / sc
            if ratio > 0.05:
                warnings.append(
                    f"{sym}: close mismatch on {ld}: lake={lc:.2f} stooq={sc:.2f} "
                    f"({ratio * 100:.1f}% diff)"
                )

    if not warnings:
        print(f"     Sanity OK — {len(reference)} reference symbols checked")

    return warnings


def _backfill_rows(
    con: duckdb.DuckDBPyConnection,
    symbol: str,
    stooq: pl.DataFrame,
    run_id: str,
    clock_now: datetime,
) -> int:
    """Insert bootstrap rows for *symbol* that don't yet exist in the lake.

    Returns count of rows inserted.
    """
    existing = {
        r[0]
        for r in con.execute(
            "SELECT effective_date FROM lake_bars WHERE security_id = ?",
            [symbol],
        ).fetchall()
    }

    to_insert = stooq.filter(~pl.col("effective_date").is_in(existing))
    if to_insert.is_empty():
        return 0

    insert_rows: list[dict[str, Any]] = []
    for row in to_insert.rows(named=True):
        insert_rows.append(
            {
                "security_id": symbol,
                "effective_date": row["effective_date"],
                "available_at": clock_now,
                "source_id": _STOOQ_SOURCE_ID,
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row["volume"],
                "source_published_at": clock_now,
                "ingested_at": clock_now,
                "validated_at": None,
                "source_fetch_id": f"bootstrap_{run_id}",
                "raw_payload_hash": "",
                "ingestion_run_id": run_id,
                "content_hash": "",
                "version_hash": "",
                "schema_version": 1,
                "parser_version": 1,
                "quality_status": "valid",
                "normalization_version": 1,
            }
        )

    if not insert_rows:
        return 0

    from alpha_lake.canonical import write_dataset

    df = pl.DataFrame(insert_rows)
    df = df.with_columns(
        pl.col("effective_date").cast(pl.Date),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("source_published_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("ingested_at").cast(pl.Datetime(time_zone="UTC")),
    )
    return write_dataset(con, "lake_bars", df)


def bootstrap_bars(con: duckdb.DuckDBPyConnection) -> int:
    """Backfill historical daily bars from the STOOQ bootstrap Parquet.

    1. Check if the Parquet exists.
    2. Run sanity checks against reference symbols.
    3. For each symbol, insert only rows not already in the lake.
    4. Returns total rows inserted.
    """
    if not _BOOTSTRAP_PARQUET.exists():
        print(f"     Bootstrap file not found: {_BOOTSTRAP_PARQUET}")
        return 0

    print(f"     Reading {_BOOTSTRAP_PARQUET}...")
    df = pl.read_parquet(str(_BOOTSTRAP_PARQUET))
    print(f"     Loaded {len(df)} rows across {df['security_id'].n_unique()} symbols")

    warnings = _sanity_check(con, df)
    for w in warnings:
        print(f"     ⚠ {w}")
    if any("mismatch" in w for w in warnings):
        print("     ❌ Sanity check FAILED — aborting bootstrap")
        return 0
    if warnings:
        print("     ⚠ Sanity warnings (non-critical) — proceeding")
    else:
        print("     ✅ Sanity check passed")

    run_id = f"stooq_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    clock_now = datetime.now(UTC)
    total = 0

    for sym in sorted(df["security_id"].unique()):
        sym_df = df.filter(pl.col("security_id") == sym).sort("effective_date")
        inserted = _backfill_rows(con, sym, sym_df, run_id, clock_now)
        if inserted:
            print(f"     {sym}: +{inserted} rows")
            total += inserted

    print(f"     Bootstrap complete: {total} new bar rows")
    return total
