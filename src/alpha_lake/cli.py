import socket
import sys

import httpx
import typer

from alpha_lake.catalog import bootstrap as bootstrap_catalog, connect
from alpha_lake.config import get_config, load_config
from alpha_lake.flows import backfill_bars, compact_dataset, ingest_bars, reparse_bars
from alpha_lake.obs import setup_otel

app = typer.Typer(name="alpha-lake")


@app.callback()
def _main():
    cfg = load_config()
    if cfg.lake.runtime == "stack":
        setup_otel()


@app.command()
def bootstrap():
    """Initialize the catalog and storage."""
    cfg = get_config()
    typer.echo("Bootstrapping Alpha-Lake catalog...")
    bootstrap_catalog(cfg)
    typer.echo("Catalog bootstrapped.")


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
    typer.echo(f"Ingested {count} bars.")
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
    typer.echo(f"Backfilled {count} bars.")
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
    typer.echo(f"Reparsed {count} rows.")
    con.close()


@app.command()
def compact(table: str = typer.Option(..., help="Table to compact")):
    """Compact a canonical table by removing duplicate versions."""
    con = connect(get_config())
    count = compact_dataset(con, table)
    typer.echo(f"Compacted {table}: {count} rows remaining.")
    con.close()


@app.command()
def health():
    """Check dataset freshness and system health."""
    cfg = get_config()
    if cfg.lake.runtime == "stack":
        _check_postgres()
        _check_rustfs()
    else:
        typer.echo(f"Runtime: {cfg.lake.runtime} (no external services to check)")
    typer.echo(f"Datasets configured: {len(cfg.quality)}")
    for name, qc in cfg.quality.items():
        typer.echo(f"  {name}: max_staleness={qc.max_staleness_days}d")


def _check_postgres() -> None:
    try:
        with socket.create_connection(("postgres", 5432), timeout=5.0):
            typer.echo("postgres: ok")
    except Exception as e:
        typer.echo(f"postgres: unreachable — {e}")
        sys.exit(1)


def _check_rustfs() -> None:
    from alpha_lake.config import get_config as _get_cfg
    cfg = _get_cfg()
    try:
        r = httpx.get(
            f"http://{cfg.s3.endpoint}/minio/health/live", timeout=5.0
        )
        if r.status_code == 200:
            typer.echo("rustfs: ok")
        else:
            typer.echo(f"rustfs: unexpected status {r.status_code}")
            sys.exit(1)
    except Exception as e:
        typer.echo(f"rustfs: unreachable — {e}")
        sys.exit(1)


@app.command()
def catalog():
    """List datasets and their status."""
    from alpha_lake.catalog import list_datasets
    con = connect(get_config())
    for ds in list_datasets(con):
        typer.echo(f"  {ds['dataset']}: v{ds['schema_version']}, {ds['rows']} rows")
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
