from __future__ import annotations

from typing import Any

import duckdb

from alpha_lake.cli_ui import info, warn
from alpha_lake.config import RootConfig
from alpha_lake.jobs.models import JobRun, JobStore


def _resolve_symbols(
    _con: Any,
    store: JobStore,
    params: dict[str, Any],
) -> list[str]:
    """Resolve ``symbols`` from params or fall back to all active symbols."""
    raw = params.get("symbols", ["active"])
    if raw == ["active"] or raw == "active":
        entries = store.list_symbols(active_only=True)
        return [e.symbol for e in entries]
    return raw


def handle_source_health(
    _con: Any,
    _cfg: RootConfig,
    _run: JobRun,
    store: JobStore,
) -> dict[str, Any]:
    """Probe each configured source: API key presence, recent call count.

    Does NOT make external HTTP calls — only checks local state.
    """
    sources = store.list_sources()
    results: list[dict[str, Any]] = []
    for s in sources:
        entry = {
            "source_id": s.source_id,
            "has_key": s.has_key,
            "hold": s.hold,
            "calls_last_min": s.calls_last_min,
            "calls_last_day": s.calls_last_day,
            "effective_rate_limit_per_sec": s.effective_rate_limit_per_sec,
            "effective_rate_limit_per_min": s.effective_rate_limit_per_min,
            "effective_rate_limit_per_day": s.effective_rate_limit_per_day,
        }
        results.append(entry)
        if s.calls_last_day and s.effective_rate_limit_per_day:
            pct = s.calls_last_day / s.effective_rate_limit_per_day * 100
            if pct > 80:
                warn(f"Source {s.source_id}: {pct:.0f}% of daily budget used")
        if not s.has_key and s.requires_key:
            warn(f"Source {s.source_id}: missing API key")
    return {"sources": results, "count": len(results)}


def handle_stooq_rebuild(
    _con: Any,
    _cfg: RootConfig,
    _run: JobRun,
    _store: JobStore,
) -> dict[str, Any]:
    """Rebuild STOOQ Parquet files from the mounted zip archive."""
    from alpha_lake.flows.bootstrap import rebuild_parquet

    symbols = rebuild_parquet()
    return {"symbols_found": len(symbols), "symbols": symbols}


def handle_indicators_compute(
    con: duckdb.DuckDBPyConnection,
    _cfg: RootConfig,
    _run: JobRun,
    _store: JobStore,
) -> dict[str, Any]:
    """Compute all technical indicators for active symbols."""
    from alpha_lake.clock import get_clock
    from alpha_lake.flows import compute_indicators

    as_of = get_clock().now()
    info(f"Computing indicators as_of={as_of}")
    row_count = compute_indicators(con, as_of=as_of)
    return {"rows_written": row_count, "as_of": as_of.isoformat()}


def handle_bars_bootstrap(
    con: duckdb.DuckDBPyConnection,
    _cfg: RootConfig,
    run: JobRun,
    store: JobStore,
) -> dict[str, Any]:
    """Backfill daily bars from STOOQ bulk Parquet for active symbols.

    Reads ``run.params_json``:
      - ``symbols``: list of symbols (default ``["active"]``)
      - ``lookback_years``: years of history (default 3)
    """
    from alpha_lake.flows.bootstrap import _backfill_stooq_bars, rebuild_parquet

    symbols = _resolve_symbols(con, store, run.params_json)
    lookback_years = run.params_json.get("lookback_years", 3)

    try:
        all_syms = rebuild_parquet()
        info(f"STOOQ rebuilt: {len(all_syms)} symbols found")
    except Exception as exc:
        warn(f"STOOQ rebuild failed: {exc}")
        return {
            "source_id": "stooq",
            "error": str(exc),
            "symbols_attempted": 0,
            "symbols_with_data": 0,
            "total_rows": 0,
            "results": [],
        }

    results: list[dict[str, Any]] = []
    total_rows = 0
    for symbol in symbols:
        try:
            rows = _backfill_stooq_bars(con, symbol, cutoff_years=lookback_years)
            total_rows += rows
            results.append({"symbol": symbol, "rows": rows})
        except Exception as exc:
            warn(f"Bootstrap failed for {symbol}: {exc}")
            results.append({"symbol": symbol, "rows": 0, "error": str(exc)})

    return {
        "source_id": "stooq",
        "symbols_attempted": len(symbols),
        "symbols_with_data": sum(1 for r in results if r.get("rows", 0) > 0),
        "total_rows": total_rows,
        "results": results,
    }


def handle_bars_refresh(
    con: duckdb.DuckDBPyConnection,
    _cfg: RootConfig,
    run: JobRun,
    store: JobStore,
) -> dict[str, Any]:
    """Refresh daily bars from the primary connector source.

    Iterates active symbols, computes missing dates per symbol, fetches
    and ingests from the connector.  If a source budget is exhausted mid-run
    the remaining symbols are deferred and ``budget_exhausted=True`` is set
    on the result.

    Reads ``run.params_json``:
      - ``symbols``: list of symbols (default ``["active"]``)
      - ``source_id``: override source (default: primary source for ``bars_daily``)
      - ``from_date`` / ``to_date``: optional date bounds (ISO strings)
    """
    import asyncio

    from alpha_lake.calendar_ import previous_trading_day
    from alpha_lake.clock import get_clock
    from alpha_lake.connectors import get_connector, has_api_key
    from alpha_lake.connectors.base import BudgetExhaustedError
    from alpha_lake.flows import _fetch_and_ingest, _missing_dates
    from alpha_lake.source_registry import get_primary_source

    symbols = _resolve_symbols(con, store, run.params_json)
    raw_src = run.params_json.get("source_id")
    default_src = get_primary_source("bars_daily") if raw_src in (None, "", "auto") else raw_src
    clock_now = get_clock().now()
    # Default to the most recent closed trading session so the refresh
    # actually fetches data for the last market day, not a no-op.
    _prev_td = previous_trading_day(clock_now.date()).isoformat()
    from_date = run.params_json.get("from_date", _prev_td)
    to_date = run.params_json.get("to_date", _prev_td)

    if not default_src:
        raise ValueError("No source configured for bars_daily")

    run_id = f"run_{clock_now.strftime('%Y%m%d_%H%M%S')}"
    total = 0
    results: list[dict[str, Any]] = []
    deferred: list[str] = []
    exhausted = False

    for symbol in symbols:
        if exhausted:
            deferred.append(symbol)
            continue

        src = default_src
        override = (
            store.get_symbol_source_override(symbol)
            if callable(getattr(store, "get_symbol_source_override", None))
            else None
        )
        if override:
            src = override.source_id

        connector = get_connector(src, "bars_daily")
        creds = has_api_key(src)
        if not (connector and creds):
            results.append({"symbol": symbol, "rows": 0, "reason": f"no_connector_for_{src}"})
            continue

        try:
            missing = _missing_dates(con, "lake_bars", symbol, from_date, to_date)
            if not missing:
                results.append({"symbol": symbol, "rows": 0, "reason": "no_missing"})
                continue

            rows = asyncio.run(
                _fetch_and_ingest(
                    con,
                    connector,
                    symbol,
                    src,
                    missing[0],
                    missing[-1],
                    run_id,
                    clock_now,
                ),
            )
            total += rows
            results.append({"symbol": symbol, "rows": rows, "source": src})
        except BudgetExhaustedError as exc:
            warn(f"Budget exhausted for {symbol} ({src}): {exc}")
            exhausted = True
            deferred.append(symbol)
            results.append({"symbol": symbol, "rows": 0, "reason": str(exc)})
        except Exception as exc:
            warn(f"Refresh failed for {symbol} ({src}): {exc}")
            results.append({"symbol": symbol, "rows": 0, "error": str(exc)})

    out: dict[str, Any] = {
        "source_id": default_src,
        "symbols_attempted": len(symbols),
        "symbols_refreshed": sum(1 for r in results if r.get("rows", 0) > 0),
        "total_rows_written": total,
        "results": results,
    }
    if deferred:
        out["deferred_symbols"] = deferred
        out["budget_exhausted"] = True
    return out


def handle_dataset_refresh(
    con: duckdb.DuckDBPyConnection,
    _cfg: RootConfig,
    run: JobRun,
    _store: JobStore,
) -> dict[str, Any]:
    """Refresh non-bars datasets from their primary connectors.

    Reads ``run.params_json``:
      - ``datasets``: list of dataset names (e.g. ``["earnings_calendar", "insider_tx"]``)
      - ``source_id``: override source (default: primary source per dataset)
      - ``from_date`` / ``to_date``: optional date bounds (ISO strings)
    """
    from alpha_lake.connectors.base import BudgetExhaustedError
    from alpha_lake.flows import ingest_dataset

    datasets = run.params_json.get("datasets", [])
    source_id = run.params_json.get("source_id")
    from_date = run.params_json.get("from_date", "")
    to_date = run.params_json.get("to_date", "")

    if not datasets:
        return {"datasets_attempted": 0, "datasets_refreshed": 0, "total_rows": 0, "results": []}

    results: list[dict[str, Any]] = []
    total = 0
    exhausted = False
    deferred: list[str] = []

    for ds in datasets:
        if exhausted:
            deferred.append(ds)
            continue

        try:
            rows = ingest_dataset(
                con=con,
                dataset=ds,
                from_date=from_date,
                to_date=to_date,
                source_id=source_id,
            )
            total += rows
            results.append({"dataset": ds, "rows": rows})
        except BudgetExhaustedError as exc:
            warn(f"Budget exhausted for dataset {ds}: {exc}")
            exhausted = True
            deferred.append(ds)
            results.append({"dataset": ds, "rows": 0, "reason": str(exc)})
        except Exception as exc:
            warn(f"Refresh failed for dataset {ds}: {exc}")
            results.append({"dataset": ds, "rows": 0, "error": str(exc)})

    out: dict[str, Any] = {
        "datasets_attempted": len(datasets),
        "datasets_refreshed": sum(1 for r in results if r.get("rows", 0) > 0),
        "total_rows_written": total,
        "results": results,
    }
    if deferred:
        out["deferred_datasets"] = deferred
        out["budget_exhausted"] = True
    return out
