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
| `price_mode` | string | no | `raw` | `raw` or `split_adjusted` |
| `snapshot_id` | string | no | — | DuckLake snapshot for pinned reads |
| `include` | string | no | — | Comma-separated extras: `provenance` to include audit columns |
| `fields` | string | no | all | Comma-separated column names to return (e.g. `date,open,high,low,close,volume`) |

\* Research reads require `as_of`. The `latest` query parameter provides an explicit non-research convenience path.

Response: JSON array of bar objects. Audit columns (`source_id`, `version_hash`, `content_hash`, `schema_version`, `parser_version`, `normalization_version`, `source_fetch_id`, `ingestion_run_id`, `raw_payload_hash`) are excluded by default; pass `?include=provenance` to include them. Use `?fields=open,high,low,close,volume` to select specific columns. `max_lookback_days` caps the query range.

#### `GET /v1/fundamentals/metrics`

Return PIT fundamental metrics for a symbol.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `symbol` | string | yes | — | Ticker symbol |
| `metric_ids` | string | no | all | Comma-separated metric IDs (e.g. `fundamentals.valuation.pe_ttm,fundamentals.profitability.gross_margin_ttm`) |
| `as_of` | datetime | yes* | — | PIT knowledge-time boundary |
| `latest` | bool | no | false | Non-research convenience path — uses current price and latest data |
| `include` | string | no | — | Comma-separated extras: `inputs`, `definitions`, `provenance` |

Response: JSON object keyed by metric ID, each with value, unit, state, tone,
label, and (if requested) input breakdown, definition, and provenance metadata.

#### `GET /v1/fundamentals/glossary`

Return the full fundamental metrics glossary — name, description, formula,
inputs, threshold profile, and surfaces for every registered metric.

Response: JSON array of metric glossary entries with embedded threshold profile.

#### `GET /v1/symbol/{symbol}/readouts`

Return PIT-correct neutral symbol readouts for a single symbol.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `symbol` | string | yes | — | Ticker symbol |
| `as_of` | datetime | yes* | — | PIT knowledge-time boundary |
| `latest` | bool | no | false | Non-research convenience path |
| `categories` | string | no | all | Comma-separated category filter |
| `readout_ids` | string | no | all | Comma-separated readout ID filter |
| `snapshot_id` | string | no | — | DuckLake snapshot for pinned reads |

Response: `{symbol, as_of, readouts: [{definition, observation}], metadata}`.
Same response shape as the dashboard readout endpoint.

#### `POST /v1/readouts/batch`

Batch readouts for multiple symbols.

| Body field | Type | Required | Description |
|-----------|------|----------|-------------|
| `symbols` | string[] | yes | List of ticker symbols |
| `as_of` | datetime | no | PIT knowledge-time boundary |
| `latest` | bool | no | Non-research convenience path |
| `categories` | string | no | Comma-separated category filter |
| `readout_ids` | string | no | Comma-separated readout ID filter |
| `snapshot_id` | string | no | DuckLake snapshot |
| `include` | string | no | — | Comma-separated extras: `provenance` to include audit columns |

Response: `{as_of, snapshot_id, items: {symbol: {...}}, errors: {symbol: str}}`. Audit columns are excluded by default.

#### `GET /v1/symbol/{symbol}/facts-bundle`

Aggregated neutral facts for a single symbol in a single response.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `symbol` | string | yes | — | Ticker symbol |
| `as_of` | datetime | yes* | — | PIT knowledge-time boundary |
| `latest` | bool | no | false | Non-research convenience path |
| `categories` | string | no | all | Comma-separated category filter |
| `readout_ids` | string | no | all | Comma-separated readout ID filter |
| `metric_ids` | string | no | all | Comma-separated fundamental metric IDs |
| `snapshot_id` | string | no | — | DuckLake snapshot |
| `include` | string | no | — | Comma-separated extras: `provenance` to include audit columns in sections |

Response sections: `price`, `readouts`, `fundamentals`, `insider_tx`,
`earnings_events`, `attention_metrics` (experimental).
Plus `freshness`, `provenance`, and `metadata` with `missing_sections`
and `experimental_sections`. Audit columns are excluded by default.

#### `POST /v1/facts-bundle/batch`

Batch facts bundle for multiple symbols.

| Body field | Type | Required | Description |
|-----------|------|----------|-------------|
| `symbols` | string[] | yes | List of ticker symbols |
| `as_of` | datetime | no | PIT knowledge-time boundary |
| `latest` | bool | no | Non-research convenience path |
| `categories` | string | no | Comma-separated category filter |
| `readout_ids` | string | no | Comma-separated readout ID filter |
| `metric_ids` | string | no | Comma-separated fundamental metric IDs |
| `snapshot_id` | string | no | DuckLake snapshot |
| `include` | string | no | — | Comma-separated extras: `provenance` to include audit columns |

#### `GET /v1/insider-transactions/{symbol}`

Return per-executive insider buy/sell transactions from Alpha Vantage.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `symbol` | string | yes | Ticker symbol |
| `as_of` | datetime | no | PIT knowledge-time boundary (defaults to now) |
| `snapshot_id` | string | no | DuckLake snapshot for pinned reads |
| `include` | string | no | — | Comma-separated extras: `provenance` to include audit columns |

Response: JSON array of insider transaction objects with `insider_name`,
`insider_title`, `transaction_type`, `shares`, `price`, `transaction_date`.

#### `GET /v1/symbols`

List symbols in the registry. Active (non-removed) by default.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `active_only` | bool | no | `true` | If `false`, also returns removed symbols |

Response: JSON array of `{symbol, added_at, added_by}` (or `removed_at` if `active_only=false`).

#### `POST /v1/symbols`

Add a symbol: validates against STOOQ data, backfills historical bars, computes indicators, registers in `_symbol_registry`.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `symbol` | string | yes | Ticker symbol |

Response: `{symbol, status: "added"|"already_active"|"restored", bars_backfilled: int}`.

#### `DELETE /v1/symbols/{symbol}`

Soft-remove a symbol: hides from dashboard UI, stops ingestion. Data stays in the lake.

Response: `{symbol, status: "removed"}`.

#### `GET /v1/bars/indicators`

Return PIT-correct bars with computed technical indicators.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `symbol` | string | yes | — | Ticker symbol |
| `indicators` | string | yes | — | Comma-separated: `sma:50,rsi:14,ema:20,bollinger:20:2` |
| `start` | date | no | — | Start effective date (inclusive) |
| `end` | date | no | — | End effective date (inclusive) |
| `as_of` | datetime | yes* | — | PIT knowledge-time boundary |
| `include` | string | no | — | Comma-separated extras: `provenance` to include audit columns |
| `fields` | string | no | all | Comma-separated column/indicator names to return (e.g. `date,close,rsi,atr`) |
Recursive indicators (RSI, EMA, ATR) receive automatic warm-up via `calendar_.shift_trading_days()` before the requested range; warm-up rows are trimmed from the response. Audit columns are excluded by default.

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
| 500 | Internal error (logged) |

## Kernel Architecture

All serving paths (Python and REST) load the kernel via `catalog.connect()`:

```python
from alpha_lake.catalog import connect
cfg = load_config("config/stack.toml")
con = connect(cfg)  # register_kernel(con) runs inside
```

The kernel consists of `CREATE OR REPLACE MACRO ... AS TABLE` definitions in `src/alpha_lake/kernel/sql/`. Each dataset contract produces one `.sql` file (e.g. `bars_pit.sql`, `bars_adjusted.sql`). CI validates kernel output schema against `contracts/*.yaml`.

## Dashboard API (dev-only)

When `[transport] dashboard_enabled = true` in `config/stack.toml`, the following
read-only endpoints are available at `/v1/dashboard/*` **without** API key auth:

| Endpoint | Params | Returns |
|---|---|---|
| `GET /v1/dashboard/datasets` | — | Array of `{dataset, tier, rows, latest_effective_date, ...}` |
| `GET /v1/dashboard/dataset/{name}` | `limit`, `as_of` | Recent rows with lineage columns |
| `GET /v1/dashboard/securities` | `q`, `limit`, `as_of` | Symbol autocomplete results |
| `GET /v1/dashboard/security/{symbol}` | `as_of` | Aggregated view across all datasets |
| `GET /v1/dashboard/snapshots` | — | Snapshot list |
| `GET /v1/dashboard/bars` | `symbol`, `start`, `end`, `as_of`, `snapshot_id` | PIT bar data |
| `GET /v1/dashboard/bars/indicators` | `symbol`, `indicators`, `start`, `end`, `as_of` | Bars with indicators |
| `GET /v1/dashboard/bars/summary` | `symbol`, `as_of`, `price_mode` | Per-symbol card (last, RSI, SMA50, ATR, MACD, trend) |
| `GET /v1/dashboard/attention/leaderboard` | `limit`, `as_of` | Sentiment leaderboard ranked by mentions |
| `GET /v1/dashboard/macro/{series_id}` | `as_of`, `start`, `end` | FRED macro series observations |
| `GET /v1/dashboard/insider/{symbol}` | `as_of`, `limit` | Insider transactions by ticker |
| `GET /v1/dashboard/analyst/{symbol}` | `as_of`, `limit` | Analyst estimate consensus (strong_buy … target_low) |
| `GET /v1/dashboard/bars/symbols` | — | Active symbols (from `_symbol_registry`) with lake data |
| `GET /v1/dashboard/indicators/glossary` | — | Full indicator glossary (name, description, formula) |
| `GET /v1/dashboard/symbol/{symbol}/fundamentals` | `as_of`, `latest`, `include` | PIT fundamental metrics by symbol (gated) |
| `GET /v1/dashboard/fundamentals/glossary` | — | Full fundamentals glossary (metric_id, name, formula, profile) |
| `GET /v1/dashboard/symbol/{symbol}/readouts` | `as_of`, `latest`, `categories`, `readout_ids` | 18 symbol readouts across 7 categories |
| `GET /v1/dashboard/health` | — | Catalog health + synthetic_mode flag |

These endpoints mirror the authenticated `/v1/*` endpoints but are gated by the
`dashboard_enabled` config flag. When disabled they return 404.

## Serve command

```bash
# Start the FastAPI server (also started by just up via compose.yaml)
just serve
# Or manually:
alpha-lake serve --host 0.0.0.0 --port 8000
```

The server serves:
- The REST API at `/v1/*`
- The Lake Watch dashboard SPA at `http://localhost:8000/`
- Static files at `/static/`
