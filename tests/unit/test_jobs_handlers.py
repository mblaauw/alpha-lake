import duckdb
import pytest

from alpha_lake.config import get_config, load_config
from alpha_lake.jobs.handlers import (
    _resolve_symbols,
    handle_bars_bootstrap,
    handle_bars_refresh,
    handle_dataset_refresh,
    handle_source_health,
)
from alpha_lake.jobs.models import JobRun
from alpha_lake.jobs.store import MemoryJobStore


@pytest.fixture(autouse=True)
def _cfg():
    load_config("config/stack.toml")
    return


# ── _resolve_symbols ────────────────────────────────────────────────────


def test_resolve_symbols_default():
    store = MemoryJobStore()
    store.add_symbol("AAPL")
    store.add_symbol("MSFT")
    store.add_symbol("GOOG", added_by="auto")
    result = _resolve_symbols(None, store, {})
    assert sorted(result) == ["AAPL", "GOOG", "MSFT"]


def test_resolve_symbols_explicit_list():
    store = MemoryJobStore()
    result = _resolve_symbols(None, store, {"symbols": ["AAPL"]})
    assert result == ["AAPL"]


def test_resolve_symbols_empty():
    store = MemoryJobStore()
    result = _resolve_symbols(None, store, {"symbols": []})
    assert result == []


# ── handle_source_health ────────────────────────────────────────────────


def test_handle_source_health():
    store = MemoryJobStore()
    cfg = get_config()
    run = JobRun(
        run_id="test",
        job_name="source.health",
        job_type="source_health",
        idempotency_key="test",
        status="running",
    )
    result = handle_source_health(None, cfg, run, store)  # type: ignore[arg-type]
    assert "sources" in result
    assert "count" in result
    assert result["count"] >= 0


# ── handle_bars_bootstrap ───────────────────────────────────────────────


def test_handle_bars_bootstrap_error():
    """STOOQ parquet files don't exist → handler returns error result."""
    store = MemoryJobStore()
    cfg = get_config()
    run = JobRun(
        run_id="test",
        job_name="bars.bootstrap",
        job_type="bars_bootstrap",
        idempotency_key="test",
        status="running",
    )
    con = duckdb.connect()
    result = handle_bars_bootstrap(con, cfg, run, store)
    assert result["source_id"] == "stooq"
    assert "error" in result
    assert result["symbols_attempted"] == 0
    assert result["symbols_with_data"] == 0
    assert result["total_rows"] == 0
    assert result["results"] == []
    con.close()


# ── handle_bars_refresh ─────────────────────────────────────────────────


def test_handle_bars_refresh_no_source():
    """When no primary source is available and no symbol override, handler returns empty result."""
    store = MemoryJobStore()
    store.add_symbol("AAPL")
    cfg = get_config()
    run = JobRun(
        run_id="test",
        job_name="bars.refresh",
        job_type="bars_refresh",
        idempotency_key="test",
        status="running",
    )
    con = duckdb.connect()
    result = handle_bars_refresh(con, cfg, run, store)
    assert result["symbols_attempted"] == 1
    assert result["total_rows_written"] == 0
    assert result["results"][0]["reason"].startswith("no_connector")
    con.close()


# ── handlers are importable ─────────────────────────────────────────────


def test_all_handlers_importable():
    from alpha_lake.jobs.handlers import (
        handle_bars_bootstrap,
        handle_bars_refresh,
        handle_dataset_refresh,
        handle_indicators_compute,
        handle_source_health,
        handle_stooq_rebuild,
    )

    assert callable(handle_bars_bootstrap)
    assert callable(handle_bars_refresh)
    assert callable(handle_dataset_refresh)
    assert callable(handle_indicators_compute)
    assert callable(handle_source_health)
    assert callable(handle_stooq_rebuild)


# ── handle_dataset_refresh ──────────────────────────────────────────────


def test_handle_dataset_refresh_empty():
    """No datasets in params returns empty result."""
    store = MemoryJobStore()
    cfg = get_config()
    run = JobRun(
        run_id="test",
        job_name="datasets.refresh.core",
        job_type="dataset_refresh",
        idempotency_key="test",
        status="running",
    )
    con = duckdb.connect()
    result = handle_dataset_refresh(con, cfg, run, store)
    assert result["datasets_attempted"] == 0
    assert result["datasets_refreshed"] == 0
    assert result["total_rows"] == 0
    con.close()


def test_handle_dataset_refresh_no_connector():
    """Datasets with no configured connector return error results."""
    store = MemoryJobStore()
    cfg = get_config()
    run = JobRun(
        run_id="test",
        job_name="datasets.refresh.core",
        job_type="dataset_refresh",
        idempotency_key="test",
        status="running",
        params_json={"datasets": ["earnings_calendar"]},
    )
    con = duckdb.connect()
    result = handle_dataset_refresh(con, cfg, run, store)
    assert result["datasets_attempted"] == 1
    assert result["datasets_refreshed"] == 0
    assert result["total_rows_written"] == 0
    con.close()
