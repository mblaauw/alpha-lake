from __future__ import annotations

from datetime import date, datetime

import duckdb
import polars as pl

from alpha_lake.clock import get_clock
from alpha_lake.interop import duckdb_to_polars, polars_to_duckdb


def _pin_snapshot(con: duckdb.DuckDBPyConnection, snapshot_id: str | None) -> None:
    if snapshot_id is not None:
        from alpha_lake.catalog import set_snapshot

        set_snapshot(con, snapshot_id)


def _ensure_kernel(con: duckdb.DuckDBPyConnection) -> None:
    try:
        con.execute("SELECT bars_asof([], '2000-01-01'::TIMESTAMPTZ)")
    except Exception:
        from alpha_lake.kernel import register_kernel

        register_kernel(con)


def pit_read(
    con: duckdb.DuckDBPyConnection,
    table: str = "lake_bars",  # noqa: ARG001
    *,
    security_ids: list[str] | None = None,
    spine: pl.DataFrame | None = None,
    as_of: datetime | None = None,
    as_of_col: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    source_precedence_dataset: str | None = None,  # noqa: ARG001
    snapshot_id: str | None = None,
) -> pl.DataFrame:
    """Unified point-in-time read across all serving modes.

    Two input modes:
    - **Security-list mode:** pass ``security_ids`` (and optionally
      ``start_date``/``end_date``). Requires ``as_of``. Returns exact
      effective-date matches within the range.
    - **Spine mode:** pass a ``spine`` DataFrame with at minimum
      ``security_id`` and ``effective_date`` columns. Requires either
      ``as_of`` (scalar PIT) or ``as_of_col`` (per-row PIT).

    Source precedence is applied via the kernel's ``_kernel_source_priority``
    table when ``source_precedence_dataset`` is given.

    Returns all columns from ``table`` plus ``security_id`` and
    ``effective_date`` (and ``as_of`` in per-row mode).
    """
    _pin_snapshot(con, snapshot_id)
    _ensure_kernel(con)

    if security_ids is not None:
        if as_of is None:
            raise ValueError("as_of is required when security_ids is provided")
        return duckdb_to_polars(
            con,
            "SELECT * FROM bars_asof(?, ?, ?, ?)",
            [security_ids, as_of, start_date, end_date],
        )

    if spine is None:
        raise ValueError("Provide either security_ids or spine")

    con.execute("DROP VIEW IF EXISTS _spine")
    con.register("_spine", spine)

    try:
        if as_of_col is not None:
            return duckdb_to_polars(
                con,
                "SELECT * FROM bars_asof_join()",
            )

        if as_of is None:
            raise ValueError("as_of is required for scalar PIT mode")

        return duckdb_to_polars(
            con,
            "SELECT * FROM bars_asof_spine(?)",
            [as_of],
        )
    finally:
        con.execute("DROP VIEW IF EXISTS _spine")


def _infer_dataset(table: str) -> str | None:
    mapping = {
        "lake_bars": "bars_daily",
        "corp_actions": "corp_actions",
        "fundamentals": "fundamentals",
        "insider_tx": "insider_tx",
        "news_articles": "news",
        "earnings_calendar": "earnings_calendar",
    }
    return mapping.get(table)


# --- Backward-compatible wrappers ---


def read_bars_asof(
    con: duckdb.DuckDBPyConnection,
    security_ids: list[str],
    as_of: datetime,
    start_date: date | None = None,
    end_date: date | None = None,
    snapshot_id: str | None = None,
) -> pl.DataFrame:
    return pit_read(
        con,
        "lake_bars",
        security_ids=security_ids,
        as_of=as_of,
        start_date=start_date,
        end_date=end_date,
        source_precedence_dataset="bars_daily",
        snapshot_id=snapshot_id,
    )


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
            con,
            security_ids,
            as_of,
            start_date,
            end_date,
            snapshot_id=snapshot_id,
        )

    raw = read_bars_asof(
        con,
        security_ids,
        as_of,
        start_date,
        end_date,
        snapshot_id=snapshot_id,
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
        con,
        security_ids,
        get_clock().now(),
        start_date,
        end_date,
        snapshot_id=snapshot_id,
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
    return pit_read(
        con,
        dataset,
        spine=spine,
        as_of=as_of,
        source_precedence_dataset=_infer_dataset(dataset),
        snapshot_id=snapshot_id,
    )


def read_asof_join(
    con: duckdb.DuckDBPyConnection,
    spine: pl.DataFrame,
    dataset: str = "lake_bars",
    snapshot_id: str | None = None,
) -> pl.DataFrame:
    """Per-row PIT join: the spine must have 'security_id', 'effective_date',
    and 'as_of' columns. Each row gets its own PIT boundary."""
    if "as_of" not in spine.columns:
        raise ValueError("Spine must have an 'as_of' column for per-row PIT")
    return pit_read(
        con,
        dataset,
        spine=spine,
        as_of_col="as_of",
        source_precedence_dataset=_infer_dataset(dataset),
        snapshot_id=snapshot_id,
    )
