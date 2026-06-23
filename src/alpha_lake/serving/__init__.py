from __future__ import annotations

from datetime import date, datetime

import duckdb
import polars as pl

from alpha_lake.clock import get_clock
from alpha_lake.interop import duckdb_to_polars


def _pin_snapshot(con: duckdb.DuckDBPyConnection, snapshot_id: str | None) -> None:
    if snapshot_id is not None:
        from alpha_lake.catalog import set_snapshot

        set_snapshot(con, snapshot_id)


def _ensure_kernel(con: duckdb.DuckDBPyConnection) -> None:
    try:
        row = con.execute(
            "SELECT 1 FROM duckdb_functions() WHERE function_name = 'bars_asof' LIMIT 1"
        ).fetchone()
        if row:
            return
    except Exception:
        pass
    from alpha_lake.kernel import register_kernel

    register_kernel(con)


def pit_read(
    con: duckdb.DuckDBPyConnection,
    table: str = "lake_bars",
    *,
    security_ids: list[str] | None = None,
    spine: pl.DataFrame | None = None,
    as_of: datetime | None = None,
    as_of_col: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    source_precedence_dataset: str | None = None,
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

    For ``lake_bars`` the dedicated DuckDB macros (``bars_asof`` etc.)
    are used. For all other tables a generic SQL PIT query is executed.

    Source precedence is applied via the kernel's ``_kernel_source_priority``
    table when ``source_precedence_dataset`` is given.
    """
    _pin_snapshot(con, snapshot_id)
    _ensure_kernel(con)

    if table == "lake_bars" and security_ids is not None:
        if as_of is None:
            raise ValueError("as_of is required when security_ids is provided")
        return duckdb_to_polars(
            con,
            "SELECT * FROM bars_asof(?, ?, ?, ?)",
            [security_ids, as_of, start_date, end_date],
        )

    if table == "lake_bars" and spine is not None:
        con.execute("DROP VIEW IF EXISTS _spine")
        con.register("_spine", spine)
        try:
            if as_of_col is not None:
                return duckdb_to_polars(con, "SELECT * FROM bars_asof_join()")
            if as_of is None:
                raise ValueError("as_of is required for scalar PIT mode")
            return duckdb_to_polars(con, "SELECT * FROM bars_asof_spine(?)", [as_of])
        finally:
            con.execute("DROP VIEW IF EXISTS _spine")

    id_col = "security_id" if table != "macro_series" else "series_id"
    id_param = "security_id" if table != "macro_series" else "series_id"

    if security_ids is not None:
        if as_of is None:
            raise ValueError("as_of is required when security_ids is provided")
        order_cols = "COALESCE(p.priority, 999), t.available_at DESC"
        if source_precedence_dataset:
            precedence_join = f"""
                LEFT JOIN _kernel_source_priority p
                    ON p.dataset = '{source_precedence_dataset}'
                   AND p.source_id = t.source_id
            """
        else:
            precedence_join = ""
            order_cols = "t.available_at DESC"
        sql = f"""
            SELECT * FROM (
                SELECT t.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY t.{id_param}, t.effective_date
                        ORDER BY {order_cols}
                    ) AS _pit_rank
                FROM {table} t
                {precedence_join}
                WHERE t.{id_param} IN ({",".join(["?"] * len(security_ids))})
                  AND t.available_at <= ?::TIMESTAMPTZ
                  AND (?::DATE IS NULL OR t.effective_date >= ?::DATE)
                  AND (?::DATE IS NULL OR t.effective_date <= ?::DATE)
            ) sub
            WHERE _pit_rank = 1
            ORDER BY {id_param}, effective_date
        """
        params = list(security_ids) + [as_of, start_date, start_date, end_date, end_date]
        return duckdb_to_polars(con, sql, params)

    if spine is not None:
        con.execute("DROP VIEW IF EXISTS _spine")
        con.register("_spine", spine)
        try:
            sql = f"""
                SELECT s.*, t.* EXCLUDE (security_id, effective_date)
                FROM _spine s
                LEFT JOIN {table} t
                    ON s.{id_col} = t.{id_param}
                   AND s.effective_date = t.effective_date
                   AND t.available_at <= s.as_of::TIMESTAMPTZ
                ORDER BY s.security_id, s.effective_date
            """
            return duckdb_to_polars(con, sql)
        finally:
            con.execute("DROP VIEW IF EXISTS _spine")

    raise ValueError("Provide either security_ids or spine")


def _infer_dataset(table: str) -> str | None:
    mapping = {
        "lake_bars": "bars_daily",
        "corp_actions": "corp_actions",
        "fundamentals": "fundamentals",
        "insider_tx": "insider_tx",
        "news_articles": "news",
        "earnings_calendar": "earnings_calendar",
        "macro_series": "macro_series",
        "economic_calendar": "economic_calendar",
        "analyst_estimates": "analyst_estimates",
        "congress_trades": "congress_trades",
        "sentiment_annotations": "sentiment_annotations",
        "attention_metrics": "attention_metrics",
        "technical_indicators": "technical_indicators",
    }
    return mapping.get(table)


# --- Backward-compatible wrappers ---


def read_macro_series_asof(
    con: duckdb.DuckDBPyConnection,
    series_ids: list[str],
    as_of: datetime,
    start_date: date | None = None,
    end_date: date | None = None,
    snapshot_id: str | None = None,
) -> pl.DataFrame:
    return pit_read(
        con,
        "macro_series",
        security_ids=series_ids,
        as_of=as_of,
        start_date=start_date,
        end_date=end_date,
        source_precedence_dataset="macro_series",
        snapshot_id=snapshot_id,
    )


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


_VALID_PRICE_MODES = frozenset({"raw", "split_adjusted"})


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
        price_mode: 'raw' (no adjustment) or 'split_adjusted' (apply splits).
    """
    if price_mode not in _VALID_PRICE_MODES:
        raise ValueError(f"Unknown price_mode '{price_mode}'. Valid: {sorted(_VALID_PRICE_MODES)}")
    _ensure_kernel(con)
    if price_mode == "raw":
        return read_bars_asof(
            con,
            security_ids,
            as_of,
            start_date,
            end_date,
            snapshot_id=snapshot_id,
        )

    return duckdb_to_polars(
        con,
        "SELECT * FROM bars_adjusted_asof(?, ?, ?, ?)",
        [security_ids, as_of, start_date, end_date],
    )


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
