import os
import socket
import sys

import typer

from alpha_lake.catalog import bootstrap as bootstrap_catalog
from alpha_lake.catalog import connect
from alpha_lake.cli_ui import (
    fail,
    info,
    ok,
    panel,
    progress,
    set_mode,
    spinner,
    table,
    warn,
)
from alpha_lake.cli_ui import (
    install_traceback as install_rich_traceback,
)
from alpha_lake.config import RootConfig, get_config, load_config
from alpha_lake.flows import (
    backfill_bars,
    compact_dataset,
    compute_indicators,
    ingest_bars,
    reparse_bars,
)

app = typer.Typer(name="alpha-lake")


@app.callback(invoke_without_command=True)
def _main(
    ctx: typer.Context,
    log_json: bool = typer.Option(False, "--log-json", help="Output structured JSON"),
):
    set_mode(log_json)
    install_rich_traceback()
    load_config()
    if ctx.invoked_subcommand is None:
        theme = "bold blue"
        panel(
            "Welcome to Alpha-Lake",
            "A stack-first, bitemporal, replayable market-data lakehouse.\n"
            "Run a command below to get started.",
            style=theme,
        )
        print(ctx.get_help())
        raise typer.Exit()


@app.command(rich_help_panel="System")
def bootstrap():
    """Initialize the catalog and storage."""
    cfg = get_config()
    _require_infra(cfg)
    with spinner("Bootstrapping catalog…"):
        bootstrap_catalog(cfg)
    panel("Bootstrap", "Catalog bootstrapped.", style="green")


@app.command(rich_help_panel="System")
def serve(
    host: str = typer.Option("0.0.0.0", "--host", envvar="AL_SERVE_HOST", help="Bind address"),
    port: int = typer.Option(8000, "--port", envvar="AL_SERVE_PORT", help="Bind port"),
):
    """Start the FastAPI server (REST API + dashboard)."""
    import uvicorn  # type: ignore[unresolved-import]

    uvicorn.run("alpha_lake.transport.app:app", host=host, port=port, reload=False)


@app.command(rich_help_panel="Data")
def ingest(
    security_id: str = typer.Option(..., help="Security ID to ingest"),
    from_date: str = typer.Option("", help="Start date (YYYY-MM-DD)"),
    to_date: str = typer.Option("", help="End date (YYYY-MM-DD)"),
    source: str = typer.Option(None, help="Source ID"),
):
    """Ingest market data for a security."""
    _require_infra(get_config())
    con = connect(get_config())
    ids = [security_id]
    with progress() as p:
        tid = p.add_task("Ingesting…", total=1)

        def _on_step(cur: int, total: int | None, label: str) -> None:
            p.update(tid, completed=cur, total=total, description=label)

        count = ingest_bars(con, ids, from_date, to_date, source, on_step=_on_step)
        p.update(tid, completed=1)
    panel("Ingest", f"Ingested [bold]{count}[/] bars for [bold]{security_id}[/].", style="green")
    con.close()


@app.command(rich_help_panel="Data")
def backfill(
    security_id: str = typer.Option(..., help="Security ID to backfill"),
    start: str = typer.Option(..., help="Start date (YYYY-MM-DD)"),
    end: str = typer.Option(..., help="End date (YYYY-MM-DD)"),
    source: str = typer.Option(None, help="Source ID"),
):
    """Backfill bars for a date range."""
    _require_infra(get_config())
    from datetime import date

    from alpha_lake.calendar_ import trading_days_in_range

    con = connect(get_config())
    ids = [security_id]
    sd = date.fromisoformat(start)
    ed = date.fromisoformat(end)
    est_total = max(1, len(list(trading_days_in_range(sd, ed))))
    with progress() as p:
        tid = p.add_task(f"Backfilling {security_id}…", total=est_total)

        def _on_step(cur: int, total: int | None, label: str) -> None:
            p.update(tid, completed=cur, total=total or est_total, description=label)

        count = backfill_bars(con, ids, sd, ed, source, on_step=_on_step)
        p.update(tid, completed=est_total)
    panel(
        "Backfill",
        f"Backfilled [bold]{count}[/] bars for [bold]{security_id}[/].",
        style="green",
    )
    con.close()


@app.command(rich_help_panel="Data")
def reparse(
    security_id: str = typer.Option(..., help="Security ID to reparse"),
    effective_date: str = typer.Option(
        None, help="Date to reparse (YYYY-MM-DD); defaults to all dates"
    ),
):
    """Reparse raw archive data for a security."""
    _require_infra(get_config())
    from datetime import date

    con = connect(get_config())
    ids = [security_id]
    ed = date.fromisoformat(effective_date) if effective_date else None
    with progress() as p:
        tid = p.add_task(f"Reparsing {security_id}…", total=None)

        def _on_step(cur: int, total: int | None, label: str) -> None:
            if total is not None:
                p.update(tid, total=total)
            p.update(tid, completed=cur, description=label)

        count = reparse_bars(con, ids, ed, on_step=_on_step)
        p.update(tid, completed=count or 0, total=count or 0)
    panel(
        "Reparse",
        f"Reparsed [bold]{count}[/] rows for [bold]{security_id}[/].",
        style="green",
    )
    con.close()


@app.command(name="dataset", rich_help_panel="Data")
def cli_ingest_dataset(
    dataset: str = typer.Option(..., help="Dataset name (e.g. macro_series)"),
    series_id: str = typer.Option(None, help="Series ID (for macro_series)"),
    security_id: str = typer.Option(None, help="Security ID (for security-based datasets)"),
    from_date: str = typer.Option("", help="Start date (YYYY-MM-DD)"),
    to_date: str = typer.Option("", help="End date (YYYY-MM-DD)"),
    source: str = typer.Option(None, help="Source ID"),
    cohort: str = typer.Option(
        "all-stocks", "--cohort", help="Cohort/channel (for attention_metrics)"
    ),
):
    """Ingest a dataset from its connector (macro_series, news, etc.)."""
    _require_infra(get_config())
    con = connect(get_config())
    from alpha_lake.flows import ingest_dataset as _ingest

    try:
        count = _ingest(
            con,
            dataset=dataset,
            series_id=series_id,
            security_id=security_id,
            from_date=from_date,
            to_date=to_date,
            source_id=source,
            cohort=cohort,
        )
        panel(
            "Ingest",
            f"Ingested [bold]{count}[/] rows for dataset [bold]{dataset}[/].",
            style="green",
        )
    except ValueError as e:
        fail(str(e))
        raise typer.Exit(code=1) from e
    finally:
        con.close()


@app.command(name="compute-indicators", rich_help_panel="Data")
def cli_compute_indicators(
    security_id: str = typer.Option(
        None, help="Security ID (optional; computes for all symbols when omitted)"
    ),
):
    """Compute all technical indicators from lake_bars and store in the lake.

    Uses wall-clock ``as_of`` because this is an interactive command, not a
    canonical pipeline step (invariant I7 exception for non-replay paths).
    """
    _require_infra(get_config())
    con = connect(get_config())
    ids = [security_id] if security_id else None
    from alpha_lake.clock import get_clock

    with progress() as p:
        tid = p.add_task("Computing indicators…", total=1)

        def _on_step(cur: int, total: int | None, label: str) -> None:
            p.update(tid, completed=cur, total=total or 1, description=label)

        count = compute_indicators(con, as_of=get_clock().now(), security_ids=ids, on_step=_on_step)
        p.update(tid, completed=1)
    panel(
        "Compute Indicators",
        f"Wrote [bold]{count}[/] indicator rows.",
        style="green",
    )
    con.close()


@app.command(rich_help_panel="Data")
def compact(table: str = typer.Option(..., help="Table to compact")):
    """Compact a canonical table by removing duplicate versions."""
    _require_infra(get_config())
    con = connect(get_config())
    with spinner(f"Compacting {table}…"):
        count = compact_dataset(con, table)
    ok(f"Compacted [bold]{table}[/]: [bold]{count}[/] rows remaining.")
    con.close()


@app.command(rich_help_panel="Validation")
def validate():
    """Validate dataset integrity and freshness (not yet implemented)."""
    warn("validate: not yet implemented — use [bold]just test[/] for validation checks.")


@app.command(rich_help_panel="Validation")
def gap_fill(
    security_id: str = typer.Option(..., help="Security ID"),
    start: str = typer.Option(..., help="Start date (YYYY-MM-DD)"),
    end: str = typer.Option(..., help="End date (YYYY-MM-DD)"),
):
    """Gap-fill missing dates for a security (not yet implemented)."""
    warn(f"gap-fill: not yet implemented for [bold]{security_id}[/] {start}–{end}.")


@app.command(rich_help_panel="Validation")
def rebuild(
    table: str = typer.Option(..., help="Table to rebuild"),
):
    """Rebuild a canonical table from raw archives (not yet implemented)."""
    warn(f"rebuild: not yet implemented for [bold]{table}[/].")


@app.command(rich_help_panel="Utilities")
def replay():
    """Run golden replay against frozen fixtures."""
    info("replay: use [bold]just replay[/] to run golden replay via pytest.")


@app.command(rich_help_panel="System")
def health():
    """Check dataset freshness and system health."""
    cfg = get_config()
    checks: dict = {"runtime": cfg.lake.runtime, "datasets": {}}
    info(f"Runtime: [bold]{cfg.lake.runtime}[/]")

    if cfg.lake.runtime == "stack":
        pg_ok = _check_postgres(return_bool=True)
        rs_ok = _check_rustfs(return_bool=True)
        checks["postgres"] = pg_ok
        checks["rustfs"] = rs_ok
    else:
        checks["runtime_check"] = "embedded"

    from alpha_lake.connectors import has_api_key

    source_rows = []
    for source_id, sc in sorted(cfg.sources.items()):
        has = has_api_key(source_id)
        if sc.requires_key and not has:
            icon = "[red]\u2717[/]"
            status = "missing API key"
        elif sc.requires_key and has:
            icon = "[green]\u2713[/]"
            status = "configured (keyed)"
        else:
            icon = "[green]\u2713[/]"
            status = "configured (keyless)"
        source_rows.append([source_id, f"{icon} {status}"])
        checks.setdefault("sources", {})[source_id] = {
            "has_key": has,
            "requires_key": sc.requires_key,
        }
    if source_rows:
        table("Sources", ["Source", "Status"], source_rows)

    rows = []
    for name, qc in cfg.quality.items():
        rows.append([name, str(qc.max_staleness_days) + "d", "", ""])
        checks["datasets"][name] = {"max_staleness_days": qc.max_staleness_days}
    table("Datasets", ["Dataset", "Max Staleness"], rows)

    from alpha_lake.catalog import catalog_health, list_datasets

    try:
        con = connect(cfg)
        hlth = catalog_health(con)
        checks["catalog"] = hlth
        s = hlth["snapshots"]
        s_id = hlth["latest_snapshot_id"]
        info(f"Snapshots: [bold]{s}[/], latest: [bold]{s_id}[/]")
        ds_rows = []
        for ds in list_datasets(con):
            ds_rows.append([ds["dataset"], str(ds["schema_version"]), str(ds["rows"])])
            checks.setdefault("datasets_list", []).append(ds)
        if ds_rows:
            table("Catalog Tables", ["Dataset", "Schema", "Rows"], ds_rows)

        # Per-source last ingestion timestamps
        from alpha_lake.canonical import DATASETS

        ingest_rows = []
        for dname, ds in sorted(DATASETS.items()):
            table_name = ds.table
            try:
                r = con.execute(
                    f"SELECT source_id, MAX(available_at)::varchar FROM {table_name} "
                    f"WHERE available_at IS NOT NULL GROUP BY source_id ORDER BY source_id"
                ).fetchall()
                for src_id, last_at in r:
                    ingest_rows.append([dname, src_id, last_at[:19] if last_at else "-"])
                    checks.setdefault("last_ingestion", {}).setdefault(src_id, {})[dname] = last_at
            except Exception:
                pass
        if ingest_rows:
            table("Last Ingestion", ["Dataset", "Source", "Last Ingested At"], ingest_rows)
        con.close()
    except Exception:
        pass


def _require_infra(cfg: RootConfig) -> None:
    """Quick connectivity check before commands that need the stack.

    In stack mode, warns and shows how to start the stack if Postgres or
    RustFS is unreachable, avoiding confusing errors deep inside DuckDB.
    """
    if cfg.lake.runtime != "stack":
        return
    pg_ok = _check_postgres(return_bool=True)
    rs_ok = _check_rustfs(return_bool=True)
    if not pg_ok or not rs_ok:
        warn(
            "Stack unreachable — run [bold]just up[/] to start it,"
            " or set [bold]AL_CI_PGHOST=localhost[/]"
            " [bold]AL_CI_RUSTFS_HOST=localhost[/] when running from the host."
        )
        sys.exit(1)


def _check_postgres(return_bool: bool = False) -> bool:
    host = os.environ.get("AL_CI_PGHOST", "postgres")
    port = int(os.environ.get("AL_CI_PGPORT", "5432"))
    label = f"postgres ({host}:{port})"
    try:
        with socket.create_connection((host, port), timeout=5.0):
            ok(f"{label}: ok")
            return True
    except Exception as e:
        fail(f"{label}: unreachable — {e}")
        if "nodename" in str(e).lower():
            info("Tip: set [bold]AL_CI_PGHOST=localhost[/] to check from the host.")
        if not return_bool:
            sys.exit(1)
        return False


def _check_rustfs(return_bool: bool = False) -> bool:
    host = os.environ.get("AL_CI_RUSTFS_HOST", "rustfs")
    port = int(os.environ.get("AL_CI_RUSTFS_PORT", "9000"))
    label = f"rustfs ({host}:{port})"
    try:
        with socket.create_connection((host, port), timeout=5.0):
            ok(f"{label}: ok")
            return True
    except Exception as e:
        fail(f"{label}: unreachable — {e}")
        if "nodename" in str(e).lower():
            info("Tip: set [bold]AL_CI_RUSTFS_HOST=localhost[/] to check from the host.")
        if not return_bool:
            sys.exit(1)
        return False


@app.command(rich_help_panel="System")
def catalog(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show snapshot details"),
):
    """List datasets and their status."""
    _require_infra(get_config())
    from alpha_lake.catalog import catalog_health, list_datasets, list_snapshots

    con = connect(get_config())
    hlth = catalog_health(con)
    info(f"Snapshots: [bold]{hlth['snapshots']}[/], latest: [bold]{hlth['latest_snapshot_id']}[/]")

    ds_rows = []
    for ds in list_datasets(con):
        ds_rows.append([ds["dataset"], str(ds["schema_version"]), str(ds["rows"])])
    if ds_rows:
        table("Datasets", ["Dataset", "Schema", "Rows"], ds_rows)

    if verbose:
        snap_rows = []
        for snap in list_snapshots(con):
            snap_rows.append(
                [f"#{snap['snapshot_id']}", str(snap["timestamp"]), str(snap["changes"])]
            )
        if snap_rows:
            table("Snapshots", ["Snapshot", "Timestamp", "Changes"], snap_rows)
    con.close()


@app.command(name="freeze-fixtures", rich_help_panel="System")
def freeze_fixtures():
    """Freeze test fixtures for golden replay."""
    from alpha_lake.fixtures import freeze as _freeze

    with spinner("Freezing fixtures…"):
        _freeze()
    ok("Fixtures frozen.")


@app.command(name="bootstrap-bars", rich_help_panel="System")
def cli_bootstrap_bars():
    """Backfill historical daily bars from the STOOQ bootstrap Parquet.

    Rebuilds STOOQ Parquet files (us_stocks.parquet, us_etfs.parquet)
    from the zip archive, seeds the _symbol_registry, and backfills any
    missing bar rows.
    """
    _require_infra(get_config())
    con = connect(get_config())
    from alpha_lake.flows.bootstrap import ensure_registry

    count = 0
    with spinner("Rebuilding STOOQ Parquet & backfilling…"):
        count = ensure_registry(con)
    if count:
        ok(f"Bootstrapped [bold]{count}[/] historical bar rows.")
    else:
        info("No new historical bars to bootstrap.")
    con.close()


# ── Operations Commands ───────────────────────────────────────────────────


@app.command(rich_help_panel="System")
def worker(
    poll_interval: float = typer.Option(5.0, "--poll-interval", help="Poll interval in seconds"),
    once: bool = typer.Option(False, "--once", help="Run once then exit"),
):
    """Start the data-job worker process."""
    _require_infra(get_config())
    from alpha_lake.jobs.scheduler import Scheduler
    from alpha_lake.jobs.store import PostgresJobStore
    from alpha_lake.jobs.worker import Worker

    cfg = get_config()
    con = connect(cfg)
    store = PostgresJobStore(con)
    sched = Scheduler(store, cfg)
    w = Worker(store, sched, cfg, poll_interval=poll_interval, once=once)
    w.run()
    con.close()


_ops_app = typer.Typer(help="Manage data-job definitions and runs")


@_ops_app.command("list")
def ops_jobs_list():
    """List configured job definitions."""
    _require_infra(get_config())
    from alpha_lake.jobs.store import PostgresJobStore

    con = connect(get_config())
    store = PostgresJobStore(con)
    jobs = store.list_job_defs()
    if not jobs:
        info("No job definitions configured.")
        con.close()
        return
    rows = []
    for j in jobs:
        status = "✓ active" if j.enabled and not j.hold else "held" if j.hold else "disabled"
        rows.append([j.job_name, j.job_type, j.schedule_kind, status, str(j.priority)])
    table("Jobs", ["Name", "Type", "Schedule", "Status", "Priority"], rows)
    con.close()


@_ops_app.command("runs")
def ops_jobs_runs(
    status: str = typer.Option(None, "--status", help="Filter by status"),
    job_name: str = typer.Option(None, "--job", help="Filter by job name"),
    limit: int = typer.Option(20, "--limit", help="Max rows"),
):
    """List recent job runs."""
    _require_infra(get_config())
    from alpha_lake.jobs.store import PostgresJobStore

    con = connect(get_config())
    store = PostgresJobStore(con)
    runs = store.list_runs(status=status, job_name=job_name, limit=limit)
    if not runs:
        info("No job runs found.")
        con.close()
        return
    rows = []
    for r in runs:
        rows.append(
            [
                r.run_id[:8],
                r.job_name,
                r.status,
                r.attempt,
                str(r.scheduled_at)[:19] if r.scheduled_at else "-",
                str(r.finished_at)[:19] if r.finished_at else "-",
            ]
        )
    table("Runs", ["ID", "Job", "Status", "Attempt", "Scheduled", "Finished"], rows)
    con.close()


@_ops_app.command("enqueue")
def ops_jobs_enqueue(
    job_name: str = typer.Option(..., "--job", help="Job name to enqueue"),
):
    """Enqueue a manual run for the given job definition."""
    _require_infra(get_config())
    from alpha_lake.jobs.scheduler import Scheduler
    from alpha_lake.jobs.store import PostgresJobStore

    con = connect(get_config())
    store = PostgresJobStore(con)
    sched = Scheduler(store, get_config())
    run = sched.enqueue_manual(job_name)
    if run:
        ok(f"Enqueued [bold]{job_name}[/] as run [bold]{run.run_id[:8]}[/].")
    else:
        warn(f"Job [bold]{job_name}[/] not found or disabled.")
    con.close()


@_ops_app.command("hold")
def ops_jobs_hold(
    job_name: str = typer.Option(..., "--job", help="Job name"),
    _reason: str = typer.Option("", "--reason", help="Reason for hold"),
):
    """Hold a job definition (prevents scheduling)."""
    _require_infra(get_config())
    from alpha_lake.jobs.store import PostgresJobStore

    con = connect(get_config())
    store = PostgresJobStore(con)
    store.update_job_def(job_name, hold=True)
    ok(f"Held [bold]{job_name}[/].")
    con.close()


@_ops_app.command("resume")
def ops_jobs_resume(
    job_name: str = typer.Option(..., "--job", help="Job name"),
):
    """Resume a held job definition."""
    _require_infra(get_config())
    from alpha_lake.jobs.store import PostgresJobStore

    con = connect(get_config())
    store = PostgresJobStore(con)
    store.update_job_def(job_name, hold=False)
    ok(f"Resumed [bold]{job_name}[/].")
    con.close()


_sources_app = typer.Typer(help="Manage source rate limits and holds")


@_sources_app.command("list")
def ops_sources_list():
    """List configured sources with limits and overrides."""
    _require_infra(get_config())
    from alpha_lake.jobs.store import PostgresJobStore

    con = connect(get_config())
    store = PostgresJobStore(con)
    sources = store.list_sources()
    if not sources:
        info("No sources configured.")
        con.close()
        return
    rows = []
    for s in sources:
        hold_mark = "held" if s.hold else ""
        rows.append(
            [
                s.source_id,
                "✓" if s.has_key else "✗",
                str(s.effective_rate_limit_per_sec) if s.effective_rate_limit_per_sec else "-",
                str(s.effective_rate_limit_per_min) if s.effective_rate_limit_per_min else "-",
                str(s.effective_rate_limit_per_day) if s.effective_rate_limit_per_day else "-",
                hold_mark,
                str(s.calls_last_min),
                str(s.calls_last_day),
            ]
        )
    table(
        "Sources",
        ["Source", "Key", "/sec", "/min", "/day", "Hold", "1m calls", "24h calls"],
        rows,
    )
    con.close()


@_sources_app.command("hold")
def ops_sources_hold(
    source_id: str = typer.Option(..., "--source", help="Source ID"),
    reason: str = typer.Option("", "--reason", help="Reason for hold"),
):
    """Hold a source (prevents jobs using it from starting)."""
    _require_infra(get_config())
    from alpha_lake.jobs.store import PostgresJobStore

    con = connect(get_config())
    store = PostgresJobStore(con)
    store.set_source_hold(source_id, hold=True, reason=reason)
    ok(f"Held source [bold]{source_id}[/].")
    con.close()


@_sources_app.command("resume")
def ops_sources_resume(
    source_id: str = typer.Option(..., "--source", help="Source ID"),
):
    """Resume a held source."""
    _require_infra(get_config())
    from alpha_lake.jobs.store import PostgresJobStore

    con = connect(get_config())
    store = PostgresJobStore(con)
    store.set_source_hold(source_id, hold=False)
    ok(f"Resumed source [bold]{source_id}[/].")
    con.close()


@_sources_app.command("set-limit")
def ops_sources_set_limit(
    source_id: str = typer.Option(..., "--source", help="Source ID"),
    per_sec: float = typer.Option(None, "--per-sec", help="Rate limit per second"),
    per_min: int = typer.Option(None, "--per-min", help="Rate limit per minute"),
    per_day: int = typer.Option(None, "--per-day", help="Rate limit per day"),
    reason: str = typer.Option("", "--reason", help="Reason"),
):
    """Override rate limits for a source."""
    _require_infra(get_config())
    from alpha_lake.jobs.store import PostgresJobStore

    con = connect(get_config())
    store = PostgresJobStore(con)
    try:
        store.set_rate_limit(
            source_id, per_sec=per_sec, per_min=per_min, per_day=per_day, reason=reason
        )
        ok(f"Updated limits for [bold]{source_id}[/].")
    except ValueError as e:
        fail(str(e))
        raise typer.Exit(code=1) from e
    finally:
        con.close()


app.add_typer(_ops_app, name="jobs")
app.add_typer(_sources_app, name="sources")


def main():
    app()


if __name__ == "__main__":
    main()
