from __future__ import annotations

import hashlib
import json
from datetime import UTC, date
from typing import Any


def mint_security_id(figi: str = "", cik: str = "", isin: str = "", composite: str = "") -> str:
    """Deterministic security_id from stable identifiers.

    Priority: FIGI > CIK > ISIN > composite.
    The composite must include exchange + native_id + first_listed_date
    when no global identifier is available.
    """
    for source_key in [figi, cik, isin, composite]:
        if source_key:
            raw = json.dumps({"source_key": source_key}, sort_keys=True, separators=(",", ":"))
            return "sec_" + hashlib.sha256(raw.encode()).hexdigest()[:24]
    return ""


def resolve(con: Any, symbol: str, as_of: date | None = None) -> str | None:
    """Resolve a symbol to security_id at a given as_of.

    Args:
        con: DuckDB connection with security_master table.
        symbol: Ticker symbol.
        as_of: Point in time for resolution. None = latest.

    Returns:
        security_id or None if not found.
    """
    if as_of:
        rows = con.execute(
            """
            SELECT security_id FROM security_master
            WHERE symbol = ?
              AND effective_start <= ?
              AND (effective_end IS NULL OR effective_end > ?)
            ORDER BY available_at DESC
            LIMIT 1
            """,
            [symbol, as_of, as_of]
        ).fetchall()
    else:
        rows = con.execute(
            """
            SELECT security_id FROM security_master
            WHERE symbol = ?
            ORDER BY available_at DESC
            LIMIT 1
            """,
            [symbol]
        ).fetchall()
    return rows[0][0] if rows else None


def register(
    con: Any,
    symbol: str,
    security_id: str,
    effective_start: date,
    available_at: Any = None,
    effective_end: date | None = None,
    figi: str = "",
    cik: str = "",
    name: str = "",
    exchange: str = "",
) -> None:
    """Register a symbol → security_id mapping."""
    from datetime import datetime, timezone
    ts = available_at or datetime.now(timezone.utc)

    con.execute("""
        CREATE TABLE IF NOT EXISTS security_master (
            security_id VARCHAR NOT NULL,
            symbol VARCHAR NOT NULL,
            name VARCHAR,
            exchange VARCHAR,
            figi VARCHAR,
            cik VARCHAR,
            effective_start DATE NOT NULL,
            effective_end DATE,
            available_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (security_id, symbol, effective_start)
        )
    """)

    con.execute(
        """
        INSERT INTO security_master
            (security_id, symbol, name, exchange, figi, cik, effective_start, effective_end, available_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [security_id, symbol, name, exchange, figi, cik, effective_start, effective_end, ts]
    )
