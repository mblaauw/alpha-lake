import json
import socket
import sys

import typer

from alpha_lake.catalog import bootstrap as bootstrap_catalog, connect
from alpha_lake.config import get_config, load_config
from alpha_lake.flows import backfill_bars, compact_dataset, ingest_bars, reparse_bars
from alpha_lake.obs import setup_otel

app = typer.Typer(name="alpha-lake")
_log_json: bool = False


def _output(message: str, data: object = None) -> None:
    if _log_json:
        record = {"message": message}
        if data is not None:
            record["data"] = data
        typer.echo(json.dumps(record))
    else:
        typer.echo(message)


@app.callback()
def _main(
    log_json: bool = typer.Option(False, "--log-json", help="Output structured JSON"),
):
    global _log_json
    _log_json = log_json
    cfg = load_config()
    if cfg.lake.runtime == "stack":
        setup_otel()


@app.command()
def bootstrap():
    """Initialize the catalog and storage."""
    cfg = get_config()
    _output("Bootstrapping Alpha-Lake catalog...")
    bootstrap_catalog(cfg)
    _output("Catalog bootstrapped.")


@app.command()
def ingest(
    security_id: str = typer.Option(..., help="Security ID to ingest"),
    from_date: str = typer.Option("", help="Start date (YYYY-MM-DD)"),
    to_date: str = typer.Option("", help="End date (YYYY-MM-DD)"),
    source: str = typer.Option(None, help="Source ID"),
):
    """Ingest market data for a security."""
    con = connect(get_config())
    count = ingest_bars(con, [security_id], from_date, to_date, source)
    _output(f"Ingested {count} bars.", data={"count": count})
    con.close()


@app.command()
def backfill(
    security_id: str = typer.Option(...),
    start: str = typer.Option(...),
    end: str = typer.Option(...),
    source: str = typer.Option(None),
):
    """Backfill bars for a date range."""
    from datetime import date
    con = connect(get_config())
    count = backfill_bars(con, [security_id], date.fromisoformat(start), date.fromisoformat(end), source)
    _output(f"Backfilled {count} bars.", data={"count": count})
    con.close()


@app.command()
def reparse(
    security_id: str = typer.Option(...),
    effective_date: str = typer.Option(None, help="YYYY-MM-DD"),
):
    """Reparse raw archive data for a security."""
    from datetime import date
    con = connect(get_config())
    ed = date.fromisoformat(effective_date) if effective_date else None
    count = reparse_bars(con, [security_id], ed)
    _output(f"Reparsed {count} rows.", data={"count": count})
    con.close()


@app.command()
def compact(table: str = typer.Option(..., help="Table to compact")):
    """Compact a canonical table by removing duplicate versions."""
    con = connect(get_config())
    count = compact_dataset(con, table)
    _output(f"Compacted {table}: {count} rows remaining.", data={"table": table, "rows": count})
    con.close()


@app.command()
def validate():
    """Validate dataset integrity and freshness (not yet implemented)."""
    _output("validate: not yet implemented — use `just test` for validation checks.")


@app.command()
def gap_fill(
    security_id: str = typer.Option(..., help="Security ID"),
    start: str = typer.Option(..., help="Start date (YYYY-MM-DD)"),
    end: str = typer.Option(..., help="End date (YYYY-MM-DD)"),
):
    """Gap-fill missing dates for a security (not yet implemented)."""
    _output(f"gap-fill: not yet implemented for {security_id} {start}–{end}.")


@app.command()
def rebuild(
    table: str = typer.Option(..., help="Table to rebuild"),
):
    """Rebuild a canonical table from raw archives (not yet implemented)."""
    _output(f"rebuild: not yet implemented for {table}.")


@app.command()
def replay():
    """Run golden replay against frozen fixtures."""
    _output("replay: use `just replay` to run golden replay via pytest.")


@app.command()
def health():
    """Check dataset freshness and system health."""
    cfg = get_config()
    checks: dict = {"runtime": cfg.lake.runtime, "datasets": {}}
    if cfg.lake.runtime == "stack":
        checks["postgres"] = _check_postgres(return_bool=True)
        checks["rustfs"] = _check_rustfs(return_bool=True)
    else:
        checks["runtime_check"] = "embedded"
    _output(f"Runtime: {cfg.lake.runtime}", data={"runtime": cfg.lake.runtime})
    _output(f"Datasets configured: {len(cfg.quality)}", data={"dataset_count": len(cfg.quality)})
    for name, qc in cfg.quality.items():
        info = {"max_staleness_days": qc.max_staleness_days}
        _output(f"  {name}: max_staleness={qc.max_staleness_days}d", data={name: info})
        checks["datasets"][name] = info

    if _log_json:
        try:
            con = connect(cfg)
            from alpha_lake.catalog import catalog_health, list_datasets
            hlth = catalog_health(con)
            checks["catalog"] = hlth
            ds_list = []
            for ds in list_datasets(con):
                ds_list.append(ds)
            checks["datasets_list"] = ds_list
            con.close()
        except Exception:
            pass
        typer.echo(json.dumps({"event": "health", "data": checks}))


def _check_postgres(return_bool: bool = False) -> bool:
    try:
        with socket.create_connection(("postgres", 5432), timeout=5.0):
            _output("postgres: ok")
            return True
    except Exception as e:
        _output(f"postgres: unreachable — {e}")
        if not return_bool:
            sys.exit(1)
        return False


def _check_rustfs(return_bool: bool = False) -> bool:
    host = "rustfs"
    port = 9000
    try:
        with socket.create_connection((host, port), timeout=5.0):
            _output(f"{host}: ok")
            return True
    except Exception as e:
        _output(f"{host}: unreachable — {e}")
        if not return_bool:
            sys.exit(1)
        return False


@app.command()
def catalog(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show snapshot details"),
):
    """List datasets and their status."""
    from alpha_lake.catalog import catalog_health, list_datasets, list_snapshots
    con = connect(get_config())
    health = catalog_health(con)
    _output(f"Snapshots: {health['snapshots']}, latest: {health['latest_snapshot_id']}",
            data={"snapshots": health})
    for ds in list_datasets(con):
        _output(f"  {ds['dataset']}: v{ds['schema_version']}, {ds['rows']} rows",
                data={"dataset": ds})
    if verbose:
        for snap in list_snapshots(con):
            _output(f"  #{snap['snapshot_id']} at {snap['timestamp']}: {snap['changes']}",
                    data={"snapshot": snap})
    con.close()


@app.command(name="freeze-fixtures")
def freeze_fixtures():
    """Freeze test fixtures for golden replay."""
    from alpha_lake.fixtures import freeze as _freeze
    _freeze()


def main():
    app()


if __name__ == "__main__":
    main()
