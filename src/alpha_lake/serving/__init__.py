from __future__ import annotations

from datetime import date, datetime

import duckdb
import polars as pl

from alpha_lake.clock import get_clock
from alpha_lake.interop import duckdb_to_polars, polars_to_duckdb
from alpha_lake.source_registry import get_source_precedence


def _pin_snapshot(con: duckdb.DuckDBPyConnection, snapshot_id: str | None) -> None:
    if snapshot_id is not None:
        from alpha_lake.catalog import set_snapshot

        set_snapshot(con, snapshot_id)


def read_bars_asof(
    con: duckdb.DuckDBPyConnection,
    security_ids: list[str],
    as_of: datetime,
    start_date: date | None = None,
    end_date: date | None = None,
    snapshot_id: str | None = None,
    ) -> pl.DataFrame:
    _pin_snapshot(con, snapshot_id)
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
    snapshot_id: str | None = None,
) -> pl.DataFrame:
    """Return bars with PIT-bounded price adjustment.

    Args:
        price_mode: 'raw' (no adjustment), 'split_adjusted' (apply splits),
                    'total_return' (apply splits + dividends).
    """
    if price_mode == "raw":
        return read_bars_asof(
            con, security_ids, as_of, start_date, end_date, snapshot_id=snapshot_id,
        )

    raw = read_bars_asof(
        con, security_ids, as_of, start_date, end_date, snapshot_id=snapshot_id,
    )
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
    snapshot_id: str | None = None,
) -> pl.DataFrame:
    """PIT-unsafe: returns newest data available as of now().

    This is an explicit non-research path. Research reads must use
    read_bars_asof() with an explicit as_of parameter.
    """
    return read_bars_asof(
        con, security_ids, get_clock().now(), start_date, end_date, snapshot_id=snapshot_id,
    )


def read_panel(
    con: duckdb.DuckDBPyConnection,
    spine: pl.DataFrame,
    as_of: datetime,
    dataset: str = "lake_bars",
    snapshot_id: str | None = None,
) -> pl.DataFrame:
    """Panel/spine reader: for each (security_id, effective_date) in the spine,
    return the newest version with available_at <= as_of.

    The spine must have columns 'security_id' and 'effective_date'.
    """
    _pin_snapshot(con, snapshot_id)
    con.execute("DROP VIEW IF EXISTS _spine")
    con.register("_spine", spine.to_arrow())
    query = f"""
        SELECT s.security_id, s.effective_date,
               b.available_at, b.source_id,
               b.open, b.high, b.low, b.close, b.volume
        FROM _spine s
        ASOF LEFT JOIN {dataset} b
            ON s.security_id = b.security_id
           AND s.effective_date >= b.effective_date
           AND ? >= b.available_at
        WHERE b.effective_date <= ?
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY s.security_id, s.effective_date
            ORDER BY b.available_at DESC
        ) = 1
    """
    result = duckdb_to_polars(con, query, [as_of, as_of.date()])
    con.execute("DROP VIEW IF EXISTS _spine")
    return result


def read_asof_join(
    con: duckdb.DuckDBPyConnection,
    spine: pl.DataFrame,
    dataset: str = "lake_bars",
    snapshot_id: str | None = None,
) -> pl.DataFrame:
    """Per-row PIT join: the spine must have 'security_id', 'effective_date',
    and 'as_of' columns. Each row gets its own PIT boundary."""
    _pin_snapshot(con, snapshot_id)
    con.execute("DROP VIEW IF EXISTS _spine")
    con.register("_spine", spine.to_arrow())
    query = f"""
        WITH joined AS (
            SELECT s.security_id, s.effective_date, s.as_of,
                   b.available_at, b.source_id,
                   b.open, b.high, b.low, b.close, b.volume,
                   ROW_NUMBER() OVER (
                       PARTITION BY s.security_id, s.effective_date, s.as_of
                       ORDER BY b.available_at DESC
                   ) AS rn
            FROM _spine s
            LEFT JOIN {dataset} b
                ON s.security_id = b.security_id
               AND b.effective_date <= s.effective_date
               AND b.available_at <= s.as_of
        )
        SELECT security_id, effective_date, as_of,
               available_at, source_id,
               open, high, low, close, volume
        FROM joined
        WHERE rn = 1
    """
    result = duckdb_to_polars(con, query, [])
    con.execute("DROP VIEW IF EXISTS _spine")
    return result
