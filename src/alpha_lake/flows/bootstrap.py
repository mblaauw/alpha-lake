from __future__ import annotations

import csv
import io
import zipfile
from contextlib import suppress
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb
import polars as pl

_ZIP_PATH = Path("/downloads/d_us_txt.zip")
_BOOTSTRAP_DIR = Path("/data/bootstrap")
_STOCKS_PARQUET = _BOOTSTRAP_DIR / "us_stocks.parquet"
_ETFS_PARQUET = _BOOTSTRAP_DIR / "us_etfs.parquet"
_REGISTRY_TABLE = "_symbol_registry"
_STOOQ_SOURCE = "stooq"
_STOOQ_SOURCE_ID = "stooq"


# ═══════════════════════════════════════════════════════════════════════
#  Parquet rebuild
# ═══════════════════════════════════════════════════════════════════════


def rebuild_parquet() -> list[str]:
    """Extract STOOQ zip into us_stocks.parquet and us_etfs.parquet.

    Each Parquet contains columns: symbol, exchange, geo, effective_date,
    open, high, low, close, volume.

    Returns sorted list of all symbols found.
    """
    _BOOTSTRAP_DIR.mkdir(parents=True, exist_ok=True)
    if not _ZIP_PATH.exists():
        print(f"  ⚠ STOOQ zip not found at {_ZIP_PATH}")
        return []

    # Fast path: skip extraction when Parquet files exist and are up to date
    zip_mtime = _ZIP_PATH.stat().st_mtime
    stocks_ok = _STOCKS_PARQUET.exists() and _STOCKS_PARQUET.stat().st_mtime >= zip_mtime
    etfs_ok = _ETFS_PARQUET.exists() and _ETFS_PARQUET.stat().st_mtime >= zip_mtime
    if stocks_ok and etfs_ok:
        symbols = set()
        if _STOCKS_PARQUET.exists():
            symbols.update(pl.read_parquet(str(_STOCKS_PARQUET))["symbol"].unique())
        if _ETFS_PARQUET.exists():
            symbols.update(pl.read_parquet(str(_ETFS_PARQUET))["symbol"].unique())
        print(f"  Skipping extraction — Parquet files are current ({len(symbols)} cached symbols)")
        return sorted(symbols)

    print(f"  Reading {_ZIP_PATH}...")
    stock_rows: list[dict[str, Any]] = []
    etf_rows: list[dict[str, Any]] = []
    all_symbols: set[str] = set()

    with zipfile.ZipFile(_ZIP_PATH) as z:
        for info in z.infolist():
            if not info.filename.endswith(".us.txt"):
                continue
            parts = info.filename.rstrip("/").split("/")
            # data/daily/{geo}/{exchange} {type}/{subfolder}/{file}
            if len(parts) < 5:
                continue
            geo = parts[2]
            exchange_type_raw = parts[3]  # e.g. "nasdaq stocks" or "nyse etfs"
            exchange, kind = exchange_type_raw.split(" ", 1)
            kind = kind.lower().replace(" ", "_")  # "stocks" or "etfs"

            if kind not in ("stocks", "etfs"):
                continue

            fname = parts[-1]
            sym = fname.replace(".us.txt", "").upper()

            content = z.read(info.filename).decode("utf-8", errors="replace")
            reader = csv.DictReader(io.StringIO(content))
            for rec in reader:
                try:
                    dt_str = rec.get("<DATE>", "")
                    if len(dt_str) != 8:
                        continue
                    dt = date(int(dt_str[:4]), int(dt_str[4:6]), int(dt_str[6:8]))
                    bar = {
                        "symbol": sym,
                        "exchange": exchange,
                        "geo": geo,
                        "effective_date": dt,
                        "open": float(rec.get("<OPEN>", 0)),
                        "high": float(rec.get("<HIGH>", 0)),
                        "low": float(rec.get("<LOW>", 0)),
                        "close": float(rec.get("<CLOSE>", 0)),
                        "volume": int(rec.get("<VOL>", 0)),
                    }
                    if kind == "stocks":
                        stock_rows.append(bar)
                    else:
                        etf_rows.append(bar)
                except (ValueError, KeyError):
                    continue
            all_symbols.add(sym)

    if stock_rows:
        pl.DataFrame(stock_rows).sort(["symbol", "effective_date"]).write_parquet(
            str(_STOCKS_PARQUET)
        )
        print(f"  Wrote {_STOCKS_PARQUET} ({len(stock_rows)} rows)")
    if etf_rows:
        pl.DataFrame(etf_rows).sort(["symbol", "effective_date"]).write_parquet(str(_ETFS_PARQUET))
        print(f"  Wrote {_ETFS_PARQUET} ({len(etf_rows)} rows)")

    return sorted(all_symbols)


# ═══════════════════════════════════════════════════════════════════════
#  Registry
# ═══════════════════════════════════════════════════════════════════════

_ops_con: duckdb.DuckDBPyConnection | None = None


def _get_ops() -> duckdb.DuckDBPyConnection:
    """Lazy-init a plain DuckDB connection for operational metadata.

    This connection avoids DuckLake entirely (which forbids PRIMARY KEY).
    """
    global _ops_con
    if _ops_con is None:
        _ops_con = duckdb.connect()
        _ops_con.execute("SET timezone = 'UTC'")
        _ops_con.execute(
            f"CREATE TABLE IF NOT EXISTS {_REGISTRY_TABLE} ("
            "  symbol VARCHAR PRIMARY KEY,"
            "  added_at TIMESTAMP WITH TIME ZONE DEFAULT now(),"
            "  removed_at TIMESTAMP WITH TIME ZONE,"
            "  added_by VARCHAR DEFAULT 'auto',"
            "  metadata VARCHAR"
            ")"
        )
    return _ops_con


def _init_registry() -> None:
    """Create _symbol_registry table if not exists, seed from lake_bars."""
    ops = _get_ops()
    with suppress(duckdb.CatalogException, Exception):
        ops.execute(
            f"INSERT OR IGNORE INTO {_REGISTRY_TABLE} (symbol, added_by) "
            "SELECT DISTINCT security_id, 'auto' FROM lake_catalog.lake_bars"
            " WHERE security_id NOT LIKE 'sec_%'"
        )


def _symbol_in_bootstrap(symbol: str) -> bool:
    """Check if *symbol* exists in either STOOQ Parquet."""
    for p in (_STOCKS_PARQUET, _ETFS_PARQUET):
        if p.exists():
            df = pl.read_parquet(str(p))
            if symbol in df["symbol"].unique():
                return True
    return False


# ═══════════════════════════════════════════════════════════════════════
#  Backfill helpers
# ═══════════════════════════════════════════════════════════════════════


def _backfill_stooq_bars(
    con: duckdb.DuckDBPyConnection,
    symbol: str,
    cutoff_years: int = 3,
) -> int:
    """Backfill up to *cutoff_years* of STOOQ bar history for *symbol*.

    Returns count of rows inserted.
    """
    from alpha_lake.canonical import write_dataset

    for p in (_STOCKS_PARQUET, _ETFS_PARQUET):
        if not p.exists():
            continue
        df = pl.read_parquet(str(p))
        sym_df = df.filter(
            pl.col("symbol") == symbol,
            pl.col("effective_date") >= date.today().replace(year=date.today().year - cutoff_years),
        ).sort("effective_date")
        if sym_df.is_empty():
            continue

        existing = {
            r[0]
            for r in con.execute(
                "SELECT effective_date FROM lake_catalog.lake_bars WHERE security_id = ?",
                [symbol],
            ).fetchall()
        }
        to_insert = sym_df.filter(~pl.col("effective_date").is_in(existing))
        if to_insert.is_empty():
            return 0

        clock_now = datetime.now(UTC)
        run_id = f"stooq_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        insert_rows = [
            {
                "security_id": symbol,
                "effective_date": r["effective_date"],
                "available_at": clock_now,
                "source_id": _STOOQ_SOURCE,
                "source_published_at": clock_now,
                "ingested_at": clock_now,
                "validated_at": None,
                "open": r["open"],
                "high": r["high"],
                "low": r["low"],
                "close": r["close"],
                "volume": r["volume"],
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
            for r in sym_df.rows(named=True)
            if r["effective_date"] not in existing
        ]
        if insert_rows:
            df_ins = pl.DataFrame(insert_rows).with_columns(
                pl.col("effective_date").cast(pl.Date),
                pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
                pl.col("source_published_at").cast(pl.Datetime(time_zone="UTC")),
                pl.col("ingested_at").cast(pl.Datetime(time_zone="UTC")),
            )
            return write_dataset(con, "lake_bars", df_ins)
    return 0


def _compute_for_symbol(con: duckdb.DuckDBPyConnection, symbol: str) -> None:
    """Compute technical indicators for a single symbol."""
    from alpha_lake.clock import get_clock
    from alpha_lake.flows import compute_indicators

    compute_indicators(con, as_of=get_clock().now(), security_ids=[symbol])


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
        stooq = bootstrap.filter(pl.col("symbol") == sym).sort("effective_date")
        if stooq.is_empty():
            warnings.append(f"{sym}: no bootstrap data")
            continue

        lake_rows = con.execute(
            "SELECT effective_date, close FROM lake_catalog.lake_bars"
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


# ═══════════════════════════════════════════════════════════════════════
#  Bootstrap bars (legacy + startup entrypoint)
# ═══════════════════════════════════════════════════════════════════════


def bootstrap_bars(con: duckdb.DuckDBPyConnection) -> int:
    """Backfill historical daily bars from STOOQ Parquet.

    Rebuilds Parquet from zip, then reads both stocks + etfs files.
    """
    _BOOTSTRAP_DIR.mkdir(parents=True, exist_ok=True)

    # Find Parquet files
    parquet_paths = [p for p in (_STOCKS_PARQUET, _ETFS_PARQUET) if p.exists()]
    if not parquet_paths:
        # Try to rebuild
        symbols = rebuild_parquet()
        if not symbols:
            print("     No STOOQ data available")
            return 0
        parquet_paths = [p for p in (_STOCKS_PARQUET, _ETFS_PARQUET) if p.exists()]

    total = 0
    for path in parquet_paths:
        print(f"     Reading {path}...")
        df = pl.read_parquet(str(path))
        df = df.rename({"symbol": "security_id"})
        print(f"     Loaded {len(df)} rows ({df['security_id'].n_unique()} symbols)")

        warnings = _sanity_check(con, df)
        for w in warnings:
            print(f"     ⚠ {w}")
        if any("mismatch" in w for w in warnings):
            print("     ❌ Sanity check FAILED — aborting bootstrap")
            return total if total > 0 else 0

        for sym in sorted(df["security_id"].unique()):
            inserted = _backfill_stooq_bars(con, sym)
            if inserted:
                print(f"     {sym}: +{inserted} rows")
                total += inserted

    print(f"     Bootstrap complete: {total} new bar rows")
    return total


def ensure_registry(con: duckdb.DuckDBPyConnection) -> int:
    """On startup/restart: rebuild Parquet, verify registry, backfill missing.

    Returns number of new symbols backfilled.
    """
    rebuild_parquet()
    _init_registry()

    ops = _get_ops()

    active = {
        r[0]
        for r in ops.execute(
            f"SELECT symbol FROM {_REGISTRY_TABLE} WHERE removed_at IS NULL"
        ).fetchall()
    }
    in_lake = {
        r[0]
        for r in con.execute(
            "SELECT DISTINCT security_id FROM lake_catalog.lake_bars"
            " WHERE security_id NOT LIKE 'sec_%'"
        ).fetchall()
    }

    for sym in in_lake:
        if sym not in active:
            ops.execute(
                f"INSERT OR IGNORE INTO {_REGISTRY_TABLE} (symbol, added_by) VALUES (?, 'auto')",
                [sym],
            )
            active.add(sym)

    total = 0
    for sym in sorted(active):
        total += _backfill_stooq_bars(con, sym)

    return total


# ═══════════════════════════════════════════════════════════════════════
#  Symbol management (used by API)
# ═══════════════════════════════════════════════════════════════════════


def add_symbol(con: duckdb.DuckDBPyConnection, symbol: str) -> dict[str, Any]:
    """Add a new symbol to the lake.

    1. Validate symbol exists in STOOQ bootstrap
    2. Check registry — if previously removed, restore
    3. Backfill bars, compute indicators, register
    """
    sym = symbol.upper().strip()
    ops = _get_ops()

    row = ops.execute(
        f"SELECT removed_at FROM {_REGISTRY_TABLE} WHERE symbol = ?", [sym]
    ).fetchone()
    if row is not None and row[0] is None:
        return {"symbol": sym, "status": "already_active"}

    if not _symbol_in_bootstrap(sym):
        raise ValueError(f"Symbol '{sym}' not found in any known data source")

    if row is not None:
        ops.execute(
            f"UPDATE {_REGISTRY_TABLE} SET removed_at = NULL, added_by = 'manual' WHERE symbol = ?",
            [sym],
        )
        return {"symbol": sym, "status": "restored"}

    count = _backfill_stooq_bars(con, sym)
    ops.execute(
        f"INSERT INTO {_REGISTRY_TABLE} (symbol, added_by) VALUES (?, 'manual')",
        [sym],
    )
    if count:
        _compute_for_symbol(con, sym)

    return {"symbol": sym, "status": "added", "bars_backfilled": count}


def remove_symbol(symbol: str) -> dict[str, Any]:
    """Soft-remove a symbol: hides from UI, stops ingestion. Data stays in lake."""
    sym = symbol.upper().strip()
    ops = _get_ops()
    ops.execute(
        f"UPDATE {_REGISTRY_TABLE} SET removed_at = now() WHERE symbol = ? AND removed_at IS NULL",
        [sym],
    )
    return {"symbol": sym, "status": "removed"}


def list_symbols(active_only: bool = True) -> list[dict[str, Any]]:
    """List symbols from the registry."""
    ops = _get_ops()
    if active_only:
        rows = ops.execute(
            f"SELECT symbol, added_at, added_by"
            f" FROM {_REGISTRY_TABLE} WHERE removed_at IS NULL ORDER BY symbol"
        ).fetchall()
        cols = ["symbol", "added_at", "added_by"]
    else:
        rows = ops.execute(
            f"SELECT symbol, added_at, removed_at, added_by FROM {_REGISTRY_TABLE} ORDER BY symbol"
        ).fetchall()
        cols = ["symbol", "added_at", "removed_at", "added_by"]

    result = []
    for r in rows:
        item = dict(zip(cols, r, strict=True))
        for k, v in item.items():
            if isinstance(v, datetime):
                item[k] = v.isoformat()
        result.append(item)
    return result
