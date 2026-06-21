# Serving API — Python Reader Contracts & REST API

The serving layer has three tiers:

1. **Kernel** — versioned SQL table macros in `src/alpha_lake/kernel/sql/*.sql`, loaded per-connection by `register_kernel(con)` inside `catalog.connect()`.
2. **Python library** — thin callers in `src/alpha_lake/serving/` that bind parameters and call kernel macros. Return Polars DataFrames.
3. **REST transport** — FastAPI endpoints with API key auth, wrapping the same kernel (via `catalog.connect()`).

## Python Reader Contracts

### Bars

| Function | Description | PIT-safe |
|----------|-------------|----------|
| `read_bars_asof(con, security_ids, as_of, ..., snapshot_id)` | Returns newest bars with `available_at <= as_of`. Optional `snapshot_id` pins DuckLake snapshot for reproducibility. | ✅ |
| `read_bars_adjusted(con, security_ids, as_of, ..., price_mode, snapshot_id)` | Like `read_bars_asof` with split adjustment | ✅ |
| `read_bars_latest(con, security_ids, ..., snapshot_id)` | Convenience — calls `read_bars_asof` with `now()` | ⚠️ Non-research |
| `read_panel(con, spine, as_of, dataset, snapshot_id)` | ASOF JOIN from spine (security_id + effective_date) | ✅ |
| `read_asof_join(con, spine, dataset, snapshot_id)` | Per-row PIT join with per-row `as_of` column | ✅ |

### Corporate Actions

| Function | Description |
|----------|-------------|
| `write_corp_actions(con, df)` | SCD2 insert with `compute_version_hash` |

### Indicators (derived)

| Function | Description |
|----------|-------------|
| `compute_indicator(con, security_id, indicator, as_of, ...)` | PIT-bounded indicator serving via REST; also available as Python function |

### Catalog & Health

| Function | Description |
|----------|-------------|
| `list_datasets(con)` | List all canonical tables with schema version and row count |
| `dataset_health(con, dataset)` | Per-dataset status, rows, latest date |
| `catalog_health(con)` | Overall catalog health: snapshot count, latest snapshot ID |
| `list_snapshots(con)` | List all DuckLake snapshots with timestamp and changes |
| `set_snapshot(con, snapshot_id)` | Pin reads to a specific DuckLake snapshot for reproducibility |
| `resolve_ingestion_run(con, run_id)` | Map ingestion_run_id to DuckLake snapshot ID |

### Dataset Read Pattern

All research readers follow this pattern:
1. Require explicit `as_of` parameter
2. Filter `available_at <= as_of`
3. Filter `effective_date <= as_of` (historical observation datasets)
4. Return newest version per natural key
5. Never default to `now()`

`latest_*` functions exist as explicit non-research convenience paths.

## REST API (FastAPI)

Base path: `/v1`

### Authentication

All endpoints require the `X-API-Key` header. Keys use prefix naming:

- `al_live_8f3a...` — production access
- `al_test_4b2c...` — test/sandbox access

Keys are bcrypt-hashed and stored via `SecretStore` (env). Managed via CLI subcommand.

### Endpoints

#### `GET /v1/bars`

Return PIT-correct OHLCV bars.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `symbol` | string | yes | — | Ticker symbol (resolved via security master) |
| `start` | date | no | — | Start effective date (inclusive) |
| `end` | date | no | — | End effective date (inclusive) |
| `as_of` | datetime | yes* | — | PIT knowledge-time boundary |
| `price_mode` | string | no | `raw` | `raw`, `split_adjusted`, or `total_return` |
| `snapshot_id` | string | no | — | DuckLake snapshot for pinned reads |

\* Research reads require `as_of`. The `latest` query parameter provides an explicit non-research convenience path.

Response: JSON array of bar objects. `max_lookback_days` caps the query range.

#### `GET /v1/bars/indicators`

Return PIT-correct bars with computed technical indicators.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `symbol` | string | yes | — | Ticker symbol |
| `indicators` | string | yes | — | Comma-separated: `sma:50,rsi:14,ema:20,bollinger:20:2` |
| `start` | date | no | — | Start effective date (inclusive) |
| `end` | date | no | — | End effective date (inclusive) |
| `as_of` | datetime | yes* | — | PIT knowledge-time boundary |
| `price_mode` | string | no | `raw` | `raw`, `split_adjusted`, or `total_return` |

Recursive indicators (RSI, EMA, ATR) receive automatic warm-up via `calendar_.shift_trading_days()` before the requested range; warm-up rows are trimmed from the response.

#### `GET /v1/health`

Dataset freshness and catalog health. No auth required (health check).

### Rate Limiting

In-pod token bucket per API key (v1). Configurable requests per second and burst size. Shared store (e.g. Redis) deferred to v2.

### Error Responses

| Status | Meaning |
|--------|---------|
| 401 | Missing or invalid API key |
| 422 | Validation error (bad parameters) |
| 429 | Rate limit exceeded |
| 500 | Internal error (logged with trace ID) |

## Kernel Architecture

All serving paths (Python and REST) load the kernel via `catalog.connect()`:

```python
from alpha_lake.catalog import connect
cfg = load_config("config/stack.toml")
con = connect(cfg)  # register_kernel(con) runs inside
```

The kernel consists of `CREATE OR REPLACE MACRO ... AS TABLE` definitions in `src/alpha_lake/kernel/sql/`. Each dataset contract produces one `.sql` file (e.g. `bars_pit.sql`, `bars_adjusted.sql`). CI validates kernel output schema against `contracts/*.yaml`.
