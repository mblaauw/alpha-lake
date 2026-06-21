# ADR-0024: Serving architecture — versioned SQL kernel, REST transport, API key auth

**Status:** Accepted

**Context:**

The serving layer currently consists of Python-only reader contracts in `src/alpha_lake/serving/__init__.py` — `pit_read()`, `read_bars_asof()`, `read_panel()`, etc. PIT resolution SQL is embedded in Python f-string templates inside `pit_read()`, making it:

- not independently testable or diffable,
- coupled to Python runtime,
- invisible to CI contract validation against `contracts/bars.v1.yaml`.

There is no remote access mechanism; every consumer must run the Python library inline. Consumers needing HTTP access (notebooks, dashboards, trading systems) have no path without embedding the full lake codebase.

During planning for the Serving Implementation epic, we identified a critical assumption error: DuckDB `CREATE OR REPLACE MACRO ... AS TABLE` creates session-scoped macros that are **not persisted** in the DuckLake catalog. The original plan of "create macros at bootstrap, available everywhere" fails because:

1. DuckDB connections are ephemeral/in-memory — a serving pod spins up a fresh instance and ATTACHes DuckLake. A macro a separate bootstrap process created lives only in that process's session catalog.
2. DuckLake's catalog is a purpose-built table catalog (columns, snapshots, data-files, stats) — it does not store DuckDB catalog objects like macros.

This means every transport (REST pod, Python library, publish job, test) that creates its own connection would get `Catalog Error: macro bars_asof does not exist`.

Additionally, the indicator warm-up mechanism specified in ADR-0017 ("an `available_at`-bounded lookback window before `start`") has no concrete implementation — `calendar_.py` lacks a `shift_trading_days` function to compute the warm-up boundary.

**Decision:**

1. **Versioned SQL kernel.** PIT resolution SQL lives in `.sql` files under `src/alpha_lake/kernel/sql/`. A `register_kernel(con)` function loads them at connection setup time. This makes the kernel:
   - a diffable, reviewable artifact,
   - testable against fixture tables in isolation,
   - loadable by every transport identically,
   - validateable against `contracts/*.yaml` in CI.

2. **Load kernel in the connection factory.** `register_kernel(con)` is called inside `catalog.connect()` after `USE lake_catalog`, before returning the connection. This removes the "did this transport remember to load the kernel?" failure mode — library, REST pod, publish job, and tests all go through `connect()`, so all get the kernel. Macro creation is in-memory metadata, microseconds, so the per-connection cost is nil.

3. **Three-layer architecture: kernel SQL → serving Python → transport.**

   ```
    kernel/sql/*.sql       — PIT resolution table macros (bars_asof, bars_pit_adjusted, ...)
   serving/__init__.py    — thin Python callers binding parameters, calling kernel macros
   transports/            — FastAPI REST (primary remote), Python library, CLI
   ```

4. **REST transport (FastAPI) as the primary remote surface.** Arrow Flight SQL / ADBC is deferred to a future bulk-optimization pass. FastAPI provides auto-generated OpenAPI docs, which are valuable for external consumers. Optional `[server]` extra in `pyproject.toml` adds `fastapi`, `uvicorn[standard]`, and `pwdlib` (bcrypt).

5. **API key authentication.** Tokens use `al_live_`/`al_test_` prefix convention, stored as bcrypt hashes via the existing `SecretStore` ABC. The `X-API-Key` header is validated in middleware before reaching any endpoint.

6. **Rate limiting.** In-pod token bucket for v1 (no external dependency). Shared store (e.g. Redis) deferred to v2 — Redis is not currently in the stack and requires operational overhead.

7. **Lookback cap.** A configurable `max_lookback_days` bound is enforced at the transport layer (in `transport/app.py`), preventing unbounded bulk queries through the REST API. The kernel SQL itself has no awareness of lookback limits.

8. **`shift_trading_days(n)` added to `calendar_.py`.** Uses `exchange_calendars`' built-in `date_to_session(dt, direction="next", count=n)` for efficient multi-step offset. Enables deterministic indicator warm-up: the indicator server prepends `shift_trading_days(start_date, -MAX_WINDOW)` trading days of history before the target range, then trims the warm-up rows from the result.

**Consequences:**

- Positive: The kernel is a versioned, diffable, testable SQL artifact. CI validates output schema against contract YAML.
- Positive: Every transport gets the same kernel automatically — structurally impossible to forget `register_kernel()`.
- Positive: Per-connection cost is microseconds (macro creation is in-memory metadata).
- Positive: REST API with OpenAPI docs lowers the barrier for external consumers (notebooks, dashboards).
- Positive: `shift_trading_days` unblocks deterministic warm-up for recursive indicators (RSI, EMA, ATR).
- Negative: REST adds server dependencies (`fastapi`, `uvicorn`, `pwdlib`) as an optional `[server]` extra.
- Negative: API key management adds operational burden (rotation, revocation, audit logging).
- Negative: Three-layer architecture is more files and indirection than the previous single-module serving layer.

**References:**

- DESIGN.md §11 (PIT read mechanics), §14 (derived indicators), §18 (Serving API), §29 (tech stack)
- `src/alpha_lake/serving/__init__.py`
- `src/alpha_lake/catalog/__init__.py` (connect factory)
- `docs/serving-api.md`
- ADR-0017 (derived indicator library — warm-up semantics)
- ADR-0009 (fact store + transform library, refined by 0017)

**Date:** 2026-06-21
