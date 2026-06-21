from __future__ import annotations

import dagster as dg

from alpha_lake.config import load_config
from alpha_lake.flows import compact_dataset, ingest_bars

_NEW_DATASETS = [
    "macro_series",
    "economic_calendar",
    "analyst_estimates",
    "congress_trades",
]

_NEW_DERIVED = [
    "technical_indicators",
    "relative_strength",
    "market_breadth",
    "vol_term_structure",
]


def _ingest_and_compact(context: dg.AssetExecutionContext, dataset: str) -> int:
    load_config()
    import duckdb

    con = duckdb.connect()
    try:
        count = compact_dataset(con, dataset)
        context.log.info(f"{dataset}: compacted {count} rows")
    except Exception:
        count = 0
    con.close()
    return count


@dg.asset(
    group_name="bars",
    compute_kind="alpha-lake",
)
def bars_daily(context: dg.AssetExecutionContext) -> int:
    """Daily bars asset — ingest bars from the primary source."""
    load_config()
    import duckdb

    con = duckdb.connect()
    count = ingest_bars(con, ["sec_test"], context.partition_key or "")
    con.close()
    context.log.info(f"Ingested {count} bars for {context.partition_key}")
    return count


@dg.asset(
    group_name="bars",
    compute_kind="alpha-lake",
    deps=[bars_daily],
)
def bars_compacted(context: dg.AssetExecutionContext) -> int:
    """Compacted bars — removes duplicate versions."""
    load_config()
    import duckdb

    con = duckdb.connect()
    count = compact_dataset(con, "lake_bars")
    con.close()
    context.log.info(f"Compacted lake_bars: {count} rows")
    return count


@dg.asset(
    group_name="quality",
    compute_kind="alpha-lake",
    deps=[bars_daily],
)
def bars_patito_check(_context: dg.AssetExecutionContext) -> dg.AssetCheckResult:
    """Asset check: Patito validation on bars."""
    from alpha_lake.models.bar_fact import BarFact

    load_config()
    import duckdb

    con = duckdb.connect()
    df = con.execute("SELECT * FROM lake_bars LIMIT 100").fetchdf()
    try:
        BarFact.validate(df)
        return dg.AssetCheckResult(passed=True)
    except Exception as e:
        return dg.AssetCheckResult(passed=False, description=str(e))
    finally:
        con.close()


# --- Phase 1 dataset ingestion assets ---

for _ds in _NEW_DATASETS:

    @dg.asset(
        group_name="ingestion",
        compute_kind="alpha-lake",
        name=_ds,
    )
    def _ingest(context: dg.AssetExecutionContext, ds: str = _ds) -> int:
        return _ingest_and_compact(context, ds)


# --- Phase 2 derived dataset assets ---

for _ds in _NEW_DERIVED:

    @dg.asset(
        group_name="derived",
        compute_kind="alpha-lake",
        name=_ds,
        deps=[bars_daily],
    )
    def _derive(context: dg.AssetExecutionContext, ds: str = _ds) -> int:
        return _ingest_and_compact(context, ds)
