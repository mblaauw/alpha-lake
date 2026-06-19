import socket
import sys

import httpx
import typer

from alpha_lake.config import get_config, load_config
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
    typer.echo("Bootstrapping Alpha-Lake catalog...")


@app.command()
def ingest(
    source: str = typer.Option(None, help="Source ID to ingest from"),
    dataset: str = typer.Option(None, help="Dataset to ingest"),
):
    """Ingest market data from sources."""


@app.command()
def health():
    """Check dataset freshness and system health."""
    cfg = get_config()

    if cfg.lake.runtime == "stack":
        _check_postgres(cfg)
        _check_rustfs(cfg)
    else:
        typer.echo(f"Runtime: {cfg.lake.runtime} (no external services to check)")

    typer.echo(f"Datasets configured: {len(cfg.quality)}")
    for name, qc in cfg.quality.items():
        typer.echo(f"  {name}: max_staleness={qc.max_staleness_days}d")


def _check_postgres(cfg) -> None:
    try:
        with socket.create_connection(("postgres", 5432), timeout=5.0):
            typer.echo("postgres: ok")
    except Exception as e:
        typer.echo(f"postgres: unreachable — {e}")
        sys.exit(1)


def _check_rustfs(cfg) -> None:
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
    typer.echo("Catalog: no datasets yet.")


@app.command()
def replay(
    run_id: str = typer.Argument(help="Ingestion run ID to replay"),
):
    """Replay an ingestion run from raw archive."""


@app.command(name="freeze-fixtures")
def freeze_fixtures():
    """Freeze test fixtures for golden replay."""


def main():
    app()


if __name__ == "__main__":
    main()
