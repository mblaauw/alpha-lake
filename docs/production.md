# Production Deployment

## Prerequisites

- Docker & Docker Compose (or compatible runtime)
- Git (for deployment via clone/pull)
- API keys for desired sources (see [docs/api-keys.md](api-keys.md))

## Quick Start

```bash
# 1. Clone & configure
git clone <repo> alpha-lake
cd alpha-lake
cp .env.example .env
# Edit .env with your API keys

# 2. Start the stack
just up

# 3. Bootstrap the catalog
just bootstrap

# 4. Verify health
just health
```

## Environment Setup

### `.env` File

Copy `.env.example` to `.env` and fill in the keys you need:

```bash
cp .env.example .env
```

Key environment variables:

| Variable | Required | Description |
|---|---|---|
| `ALPHA_LAKE_EODHD_API_KEY` | For bars | EODHD historical data |
| `ALPHA_LAKE_TIINGO_API_KEY` | Optional | Tiingo bars/fundamentals |
| `ALPHA_LAKE_FINNHUB_API_KEY` | Optional | News/sentiment/insider |
| `ALPHA_LAKE_MARKETAUX_API_KEY` | Optional | News/sentiment |
| `ALPHA_LAKE_FMP_API_KEY` | Optional | Economic calendar/analyst |
| `ALPHA_LAKE_ALPACA_API_KEY_ID` | Optional | Alpaca bars |
| `ALPHA_LAKE_SEC_CONTACT_EMAIL` | Recommended | SEC EDGAR access |

### Without Docker

For embedded/local development:

```bash
# Install uv (if not installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Sync dependencies
uv sync --group dev

# Use embedded config
export ALPHA_LAKE_CONFIG=config/embedded.toml
```

## Stack Architecture

```
┌─────────────┐    ┌──────────┐    ┌───────────┐
│  app (CLI)  │───▶│ DuckDB   │───▶│  Postgres │
│             │    │ (engine) │    │ (catalog) │
└─────────────┘    └──────────┘    └───────────┘
                         │
                    ┌────▼────┐
                    │ RustFS  │
                    │  (S3)   │
                    └─────────┘
```

- **Postgres**: Metadata catalog (schemas, snapshots, source priorities)
- **RustFS**: S3-compatible object storage for raw archives and canonical data
- **DuckDB**: Query engine (embedded or via Postgres adapter)
- **App**: CLI container — stateless, exits after each command

## Running Ingestion

### Bars (Market Data)

```bash
# Ingest a single security
just ingest --security-id AAPL --from-date 2026-01-01 --to-date 2026-06-22

# Backfill date range
docker compose run --rm app backfill-bars --security-ids AAPL,MSFT --start-date 2026-01-01 --end-date 2026-06-01
```

### Generic Datasets

```bash
# Macro series (FRED, keyless)
docker compose run --rm app dataset --dataset macro_series --series-id GDP

# News (via Finnhub or Marketaux)
docker compose run --rm -e ALPHA_LAKE_FINNHUB_API_KEY=$KEY app dataset --dataset news --security-id AAPL --from-date 2026-06-20 --to-date 2026-06-22

# Sentiment
docker compose run --rm -e ALPHA_LAKE_MARKETAUX_API_KEY=$KEY app dataset --dataset sentiment --security-id AAPL --source marketaux --from-date 2026-06-20 --to-date 2026-06-22

# Attention metrics (ApeWisdom, keyless)
docker compose run --rm app dataset --dataset attention_metrics --security-id AAPL --source apewisdom
```

## Health Monitoring

### `just health`

Shows:
- Runtime mode (stack/embedded)
- Postgres & RustFS connectivity
- Per-source API key status (✓ keyed / ✓ keyless / ✗ missing)
- Dataset staleness windows
- Catalog table row counts
- Last ingestion timestamps per dataset per source

### Structured Logging

Pass `--log-json` to any command for JSON-structured output:

```bash
docker compose run --rm app --log-json health
```

### Expected Output

```json
{"event": "source_status", "source_id": "finnhub", "has_key": true, "requires_key": true}
{"event": "dataset_staleness", "dataset": "bars", "max_staleness_days": 2}
```

## Rate Limits

Sources have configured rate limits matching their free-tier API caps:

| Source | Limit (free) | Configured |
|---|---|---|
| EODHD | 1000 req/day | 10/sec, 1000/day |
| Tiingo | 500 req/day, 30 req/min | 0.5/sec, 30/min, 500/day |
| Alpaca | 200 req/min | 1/sec, 200/min |
| Finnhub | 60 req/min | 1/sec, 55/min |
| FMP | 250 req/day | 5/sec, 250/day |
| FRED | 120 req/min (keyless) | 5/sec, 120000/day |
| Marketaux | 100 req/day | 1/sec, 100/day |
| OpenFIGI | 20 req/min | 0.33/sec, 20/min |
| SEC | 10 req/sec | 10/sec |
| StockTwits | 200 req/hour | 1/sec |
| Quiver | 100 req/day | 1/sec, 100/day |
| Reddit | 10 req/min (OAuth) | 1/sec, 10/min |
| ApeWisdom | Unknown (keyless) | 1/sec |

## Backup & Recovery

### Catalog (Postgres)

```bash
# Dump
docker compose exec -T postgres pg_dump -U lake lake_catalog > backup_catalog.sql

# Restore
docker compose exec -T postgres psql -U lake lake_catalog < backup_catalog.sql
```

### Raw Archives & Canonical Data (RustFS/S3)

```bash
# Back up the RustFS data volume
docker run --rm -v alpha-lake_rustfs-data:/data -v $(pwd):/backup alpine tar czf /backup/rustfs_backup.tar.gz /data

# Or use AWS CLI for S3-backed storage:
aws s3 sync s3://lake/backups/ s3://lake/ --profile alpha-lake
```

### Point-in-Time Recovery

Canonical data is tri-temporal — historical queries using `as_of` work automatically.
Full replay from raw archives is supported:

```bash
just replay
```

## Troubleshooting

### "Config not loaded"

Ensure `config/stack.toml` exists and is valid TOML:

```bash
docker compose run --rm app health
```

### "Stack unreachable"

Start the stack containers:

```bash
just up
```

### "Missing API key"

Keys are read from `ALPHA_LAKE_<SOURCE>_API_KEY` environment variables.
Set them in `.env` or pass via `-e` to `docker compose run`:

```bash
docker compose run --rm -e ALPHA_LAKE_FINNHUB_API_KEY=$KEY app dataset ...
```

### Ingestion fails with HTTP 429

Rate limit exceeded. Check `just health` for configured limits and
wait before retrying. Reduce concurrency or increase `rate_limit_per_sec`
in `config/stack.toml` if you have a higher-tier API plan.

### Container exits immediately

The `app` container is stateless — it runs the CLI command and exits.
Use `docker compose run --rm app <command>` instead of `exec`.

## Dagster Integration (Optional)

Dagster support is defined in ``src/alpha_lake/dagster_assets.py`` but the
Dagster Compose overlay is not yet published. To run Dagster:

```bash
# TBD — dagster compose overlay not yet implemented
```

See ``src/alpha_lake/dagster_assets.py`` for the defined assets.
