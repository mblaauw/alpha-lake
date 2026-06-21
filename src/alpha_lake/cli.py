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
from alpha_lake.flows import backfill_bars, compact_dataset, ingest_bars, reparse_bars

app = typer.Typer(name="alpha-lake")


@app.callback()
def _main(
    log_json: bool = typer.Option(False, "--log-json", help="Output structured JSON"),
):
    set_mode(log_json)
    install_rich_traceback()
    load_config()


@app.command()
def bootstrap():
    """Initialize the catalog and storage."""
    cfg = get_config()
    _require_infra(cfg)
    with spinner("Bootstrapping catalog…"):
        bootstrap_catalog(cfg)
    panel("Bootstrap", "Catalog bootstrapped.", style="green")


@app.command()
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


@app.command()
def backfill(
    security_id: str = typer.Option(...),
    start: str = typer.Option(...),
    end: str = typer.Option(...),
    source: str = typer.Option(None),
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


@app.command()
def reparse(
    security_id: str = typer.Option(...),
    effective_date: str = typer.Option(None, help="YYYY-MM-DD"),
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


@app.command()
def compact(table: str = typer.Option(..., help="Table to compact")):
    """Compact a canonical table by removing duplicate versions."""
    _require_infra(get_config())
    con = connect(get_config())
    with spinner(f"Compacting {table}…"):
        count = compact_dataset(con, table)
    ok(f"Compacted [bold]{table}[/]: [bold]{count}[/] rows remaining.")
    con.close()


@app.command()
def validate():
    """Validate dataset integrity and freshness (not yet implemented)."""
    warn("validate: not yet implemented — use [bold]just test[/] for validation checks.")


@app.command()
def gap_fill(
    security_id: str = typer.Option(..., help="Security ID"),
    start: str = typer.Option(..., help="Start date (YYYY-MM-DD)"),
    end: str = typer.Option(..., help="End date (YYYY-MM-DD)"),
):
    """Gap-fill missing dates for a security (not yet implemented)."""
    warn(f"gap-fill: not yet implemented for [bold]{security_id}[/] {start}–{end}.")


@app.command()
def rebuild(
    table: str = typer.Option(..., help="Table to rebuild"),
):
    """Rebuild a canonical table from raw archives (not yet implemented)."""
    warn(f"rebuild: not yet implemented for [bold]{table}[/].")


@app.command()
def replay():
    """Run golden replay against frozen fixtures."""
    info("replay: use [bold]just replay[/] to run golden replay via pytest.")


@app.command()
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
        warn("Stack unreachable — run [bold]just up[/] to start it.")
        sys.exit(1)


def _check_postgres(return_bool: bool = False) -> bool:
    try:
        with socket.create_connection(("postgres", 5432), timeout=5.0):
            ok("postgres: ok")
            return True
    except Exception as e:
        fail(f"postgres: unreachable — {e}")
        if not return_bool:
            sys.exit(1)
        return False


def _check_rustfs(return_bool: bool = False) -> bool:
    host = "rustfs"
    port = 9000
    try:
        with socket.create_connection((host, port), timeout=5.0):
            ok(f"{host}: ok")
            return True
    except Exception as e:
        fail(f"{host}: unreachable — {e}")
        if not return_bool:
            sys.exit(1)
        return False


@app.command()
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


@app.command(name="freeze-fixtures")
def freeze_fixtures():
    """Freeze test fixtures for golden replay."""
    from alpha_lake.fixtures import freeze as _freeze

    with spinner("Freezing fixtures…"):
        _freeze()
    ok("Fixtures frozen.")


def main():
    app()


if __name__ == "__main__":
    main()
