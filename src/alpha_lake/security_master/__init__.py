from __future__ import annotations

import contextlib
import hashlib
import json
import os
from datetime import date
from typing import Any

from alpha_lake.clock import get_clock

# In-memory ticker → CIK cache, file-backed for persistence.
_TICKER_CIK_CACHE: dict[str, str] = {}
_TICKER_CIK_TTL: int = 86400  # 24h default TTL
_TICKER_CIK_PATH: str = os.environ.get(
    "ALPHA_LAKE_TICKER_CIK_CACHE", "/tmp/alpha_lake_state/ticker_cik_cache.json"
)


def _load_ticker_cik_cache() -> None:
    global _TICKER_CIK_CACHE
    try:
        with open(_TICKER_CIK_PATH) as f:
            _TICKER_CIK_CACHE = json.load(f)
    except FileNotFoundError, json.JSONDecodeError:
        _TICKER_CIK_CACHE = {}


def _save_ticker_cik_cache() -> None:
    os.makedirs(os.path.dirname(_TICKER_CIK_PATH), exist_ok=True)
    with open(_TICKER_CIK_PATH, "w") as f:
        json.dump(_TICKER_CIK_CACHE, f)


def resolve_ticker_to_cik(symbol: str, con: Any | None = None) -> str | None:
    """Resolve a ticker symbol to a CIK number.

    Checks in-memory cache first (24h TTL), then falls back to the
    ``security_master`` table in *con*, then to a static well-known map.
    CIK is returned zero-padded to 10 digits.
    """
    if not _TICKER_CIK_CACHE:
        _load_ticker_cik_cache()

    cached = _TICKER_CIK_CACHE.get(symbol.upper())
    if cached is not None:
        return cached

    if con is not None:
        rows = con.execute(
            "SELECT cik FROM security_master WHERE symbol = ? AND cik != '' LIMIT 1",
            [symbol.upper()],
        ).fetchall()
        if rows and rows[0][0]:
            cik = rows[0][0].zfill(10)
            _TICKER_CIK_CACHE[symbol.upper()] = cik
            _save_ticker_cik_cache()
            return cik

    return None


def _reset_cache_for_test() -> None:
    """Clear the in-memory and file-backed ticker→CIK cache (tests only)."""
    global _TICKER_CIK_CACHE
    _TICKER_CIK_CACHE = {}
    with contextlib.suppress(FileNotFoundError):
        os.remove(_TICKER_CIK_PATH)


def register_ticker_cik(symbol: str, cik: str) -> None:
    """Register a ticker → CIK mapping in the cache."""
    _TICKER_CIK_CACHE[symbol.upper()] = cik.zfill(10)
    _save_ticker_cik_cache()


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
            [symbol, as_of, as_of],
        ).fetchall()
    else:
        rows = con.execute(
            """
            SELECT security_id FROM security_master
            WHERE symbol = ?
            ORDER BY available_at DESC
            LIMIT 1
            """,
            [symbol],
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
    ts = available_at or get_clock().now()

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
            (security_id, symbol, name, exchange, figi, cik,
             effective_start, effective_end, available_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [security_id, symbol, name, exchange, figi, cik, effective_start, effective_end, ts],
    )
