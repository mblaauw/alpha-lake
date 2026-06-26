---
name: rest-transport
description: Alpha-Lake REST transport — FastAPI endpoints, API key auth, token bucket rate limiting, lookback cap, health endpoint. Use when modifying transport/app.py, adding endpoints, or changing auth/rate-limit behavior.
---

# REST Transport

The REST API is served by FastAPI (optional `[server]` extra). All endpoints go through `catalog.connect()` → `register_kernel()`, so the kernel is always present.

## File

`src/alpha_lake/transport/app.py` — single-file FastAPI app.

## Key Patterns

### Auth

```python
key = request.headers.get("X-API-Key") or request.headers.get("Authorization", "").removeprefix("Bearer ")
```

Keys use prefix naming: `al_live_` (production), `al_test_` (test/sandbox).
Stored as bcrypt hashes via the existing `SecretStore` ABC.
`/v1/health` does NOT require auth.

### Rate Limit

In-pod token bucket (`_TokenBucket`) per API key. Configurable rate/burst in code (v1).
Shared store (Redis) deferred to v2.

### Lookback Cap

```python
_MAX_LOOKBACK_DAYS = 365 * 3  # 3 years
```

Enforced **in transport** before calling the kernel — the kernel SQL has no awareness of lookback limits.
If `(end - start).days > _MAX_LOOKBACK_DAYS`, return HTTP 422.

### Warm-Up for Recursive Indicators

The indicators endpoint prepends warm-up history before the target range, then trims warm-up rows from the response:

```python
warmup_start = shift_trading_days(start, -(window * multiplier), exchange="XNYS")
```

## Endpoints

### Authenticated (`_auth()` required)

| Path | Params |
|------|--------|
| `GET /v1/bars` | symbol, start, end, as_of, snapshot_id, price_mode |
| `GET /v1/bars/indicators` | symbol, indicators, start, end, as_of, price_mode, snapshot_id |
| `GET /v1/fundamentals/metrics` | symbol, as_of, snapshot_id, categories, metric_ids, include, price_mode |
| `GET /v1/fundamentals/glossary` | categories |
| `GET /v1/insider-transactions/{symbol}` | as_of, snapshot_id |
| `GET /v1/earnings-calendar` | from_date, to_date |
| `GET /v1/attention-metrics/{symbol}` | as_of, limit |
| `GET /v1/decision-panel` | symbols, as_of, snapshot_id |
| `GET /v1/dataset-health` | — |
| `GET /v1/contract` | dataset |
| `GET /v1/universe` | q, asset_type |
| `GET /v1/trading-calendar` | year |
| `GET /v1/health` | — (no auth) |

### Dashboard (`dashboard_enabled` gated, no auth)

All dashboard routes are in `transport/dashboard.py` with a separate `APIRouter`. Gated behind `[transport] dashboard_enabled`.

| Path | Params |
|------|--------|
| `GET /v1/dashboard/health` | — |
| `GET /v1/dashboard/datasets` | — |
| `GET /v1/dashboard/dataset/{name}` | limit, as_of |
| `GET /v1/dashboard/securities` | q, limit, as_of |
| `GET /v1/dashboard/security/{symbol}` | as_of |
| `GET /v1/dashboard/snapshots` | — |
| `GET /v1/dashboard/bars` | symbol, start, end, as_of, snapshot_id, price_mode |
| `GET /v1/dashboard/bars/symbols` | — |
| `GET /v1/dashboard/bars/summary` | symbol, as_of, price_mode |
| `GET /v1/dashboard/bars/indicators` | symbol, indicators, start, end, as_of |
| `GET /v1/dashboard/indicators/glossary` | — |
| `GET /v1/dashboard/attention/leaderboard` | limit, as_of |
| `GET /v1/dashboard/insider/{symbol}` | as_of, limit |
| `GET /v1/dashboard/analyst/{symbol}` | as_of, limit |
| `GET /v1/dashboard/macro/{series_id}` | as_of, start, end |
| `GET /v1/dashboard/news/{symbol}` | as_of, limit |
| `GET /v1/dashboard/symbol/{symbol}/fundamentals` | as_of, latest, include |
| `GET /v1/dashboard/fundamentals/glossary` | categories |
| `GET /v1/dashboard/symbol/{symbol}/readouts` | as_of, latest, categories, readout_ids |

### Static (no auth)

| Path | File |
|------|------|
| `GET /` | `static/index.html` |
| `GET /manifest.webmanifest` | `static/manifest.webmanifest` |
| `GET /service-worker.js` | `static/service-worker.js` |

## Forbidden

- Do not add endpoints that accept `as_of = NULL` for research paths (use explicit `latest` query param).
- Do not override `_MAX_LOOKBACK_DAYS` without config-driven mechanism.
- Do not bypass `_auth()` on data endpoints.
- Do not access the DuckDB connection outside of `_get_con()` (creates lazy singleton).

## Gates

```bash
rg -n "as_of.*None|as_of.*null|as_of.*NULL" src/alpha_lake/transport/
just lint
```
