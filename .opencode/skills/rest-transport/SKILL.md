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

| Path | Auth | Params |
|------|------|--------|
| `GET /v1/bars` | Required | symbol, start, end, as_of, snapshot_id |
| `GET /v1/bars/indicators` | Required | symbol, indicators, start, end, as_of |
| `GET /v1/health` | None | — |

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
