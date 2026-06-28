from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import duckdb

from alpha_lake.cli_ui import info, warn
from alpha_lake.config import RootConfig
from alpha_lake.jobs.models import JobRun, JobStore


def _utcnow() -> datetime:
    return datetime.now(UTC)


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
