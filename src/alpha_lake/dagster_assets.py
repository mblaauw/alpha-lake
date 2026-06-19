from __future__ import annotations


import dagster as dg

from alpha_lake.config import load_config
from alpha_lake.flows import backfill_bars, compact_dataset, ingest_bars


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
def bars_patito_check(context: dg.AssetExecutionContext) -> dg.AssetCheckResult:
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
