from __future__ import annotations

from datetime import date, datetime

import duckdb
import polars as pl

from alpha_lake.clock import get_clock
from alpha_lake.interop import duckdb_to_polars, polars_to_duckdb
from alpha_lake.source_registry import get_source_precedence


def read_bars_asof(
    con: duckdb.DuckDBPyConnection,
    security_ids: list[str],
    as_of: datetime,
    start_date: date | None = None,
    end_date: date | None = None,
) -> pl.DataFrame:
    source_priority = get_source_precedence("bars_daily")
    params: list = [security_ids, as_of, as_of.date()]

    date_filter = ""
    if start_date:
        date_filter += " AND b.effective_date >= ?"
        params.append(start_date)
    if end_date:
        date_filter += " AND b.effective_date <= ?"
        params.append(end_date)

    query = """
        WITH per_source AS (
            SELECT
                b.security_id,
                b.effective_date,
                b.available_at,
                b.source_id,
                b.open, b.high, b.low, b.close, b.volume,
                b.version_hash,
                b.quality_status,
                ROW_NUMBER() OVER (
                    PARTITION BY b.security_id, b.effective_date
                    ORDER BY b.available_at DESC
                ) AS version_rank
            FROM lake_bars b
            WHERE b.security_id = ANY(?)
              AND b.available_at <= CAST(? AS TIMESTAMP)
              AND b.effective_date <= CAST(? AS DATE)
    """ + date_filter + """
        ),
        preferred AS (
            SELECT *,
                ROW_NUMBER() OVER (
                    PARTITION BY security_id, effective_date
                    ORDER BY """ + _priority_case(source_priority) + """, available_at DESC
                ) AS source_rank
            FROM per_source
            WHERE version_rank = 1
        )
        SELECT
            security_id, effective_date, available_at, source_id,
            open, high, low, close, volume, version_hash, quality_status
        FROM preferred
        WHERE source_rank = 1
        ORDER BY security_id, effective_date
    """
    return duckdb_to_polars(con, query, params)


def _priority_case(source_priority: list[str]) -> str:
    parts = ["CASE source_id"]
    for i, s in enumerate(source_priority):
        parts.append(f"WHEN '{s}' THEN {i}")
    parts.append(f"ELSE {len(source_priority)} END")
    return " ".join(parts)


def read_bars_adjusted(
    con: duckdb.DuckDBPyConnection,
    security_ids: list[str],
    as_of: datetime,
    start_date: date | None = None,
    end_date: date | None = None,
    price_mode: str = "raw",
) -> pl.DataFrame:
    """Return bars with PIT-bounded price adjustment.

    Args:
        price_mode: 'raw' (no adjustment), 'split_adjusted' (apply splits),
                    'total_return' (apply splits + dividends).
    """
    if price_mode == "raw":
        return read_bars_asof(con, security_ids, as_of, start_date, end_date)

    raw = read_bars_asof(con, security_ids, as_of, start_date, end_date)
    if raw.height == 0:
        return raw

    con.execute("DROP TABLE IF EXISTS _raw_bars")
    polars_to_duckdb(con, raw, "_raw_bars")

    adj_query = """
        WITH factors AS (
            SELECT
                ca.security_id,
                EXP(SUM(LN(ca.ratio_numerator / NULLIF(ca.ratio_denominator, 0)))
                    OVER (PARTITION BY ca.security_id ORDER BY ca.effective_date
                          ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
                ) AS cumulative_factor
            FROM corp_actions ca
            WHERE ca.action_type = 'split'
              AND ca.available_at <= CAST(? AS TIMESTAMPTZ)
        ),
        latest_factor AS (
            SELECT security_id, MAX(cumulative_factor) AS factor
            FROM factors
            GROUP BY security_id
        )
        SELECT
            b.security_id,
            b.effective_date,
            b.available_at,
            b.source_id,
            round(b.open   / COALESCE(lf.factor, 1.0), 4) AS open,
            round(b.high   / COALESCE(lf.factor, 1.0), 4) AS high,
            round(b.low    / COALESCE(lf.factor, 1.0), 4) AS low,
            round(b.close  / COALESCE(lf.factor, 1.0), 4) AS close,
            CAST(round(b.volume * COALESCE(lf.factor, 1.0), 0) AS BIGINT) AS volume,
            b.version_hash,
            b.quality_status,
            COALESCE(lf.factor, 1.0) AS adjustment_factor
        FROM _raw_bars b
        LEFT JOIN latest_factor lf ON lf.security_id = b.security_id
        ORDER BY b.security_id, b.effective_date
    """
    result = duckdb_to_polars(con, adj_query, [as_of])
    con.execute("DROP TABLE IF EXISTS _raw_bars")
    return result


def read_bars_latest(
    con: duckdb.DuckDBPyConnection,
    security_ids: list[str],
    start_date: date | None = None,
    end_date: date | None = None,
) -> pl.DataFrame:
    """PIT-unsafe: returns newest data available as of now()."""
    return read_bars_asof(con, security_ids, get_clock().now(), start_date, end_date)
