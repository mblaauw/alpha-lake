# Alpha-Lake Data Job Worker Design

**Status:** Proposed implementation design  
**Date:** 2026-06-28  
**Audience:** OpenCode implementation agent  
**Primary goal:** Move automated data updates, scheduled refreshes, and long-running bootstrap work out of HTTP request handlers and server startup while preserving Alpha-Lake's point-in-time and replay invariants.

## Summary

Alpha-Lake should add a small data-job worker service. The worker is not a strategy worker and is not a generic user command bus. It is an operational runner for lake-owned data jobs:

- refresh configured datasets,
- bootstrap or gap-fill historical bars,
- compute derived neutral facts after new source data arrives,
- rebuild local bulk-import artifacts such as STOOQ Parquet,
- expose job status, schedules, holds, and source rate-limit safety controls.

The API should let operators observe and control configured jobs. It should not become an arbitrary "submit any job" endpoint. The worker should claim already-configured due work, execute one job at a time by calling existing `flows/` functions, persist status/outcomes, and enforce source budgets before connector calls.

## Background

Alpha-Lake already has the right design principle in ADR-0010: pipeline logic lives once in `flows/`; CLI, API, tests, and future orchestration shells call those flows. The worker must follow that rule.

Current operational pain points:

- `POST /v1/symbols` performs validation, backfill, indicator computation, and registry updates synchronously.
- Server startup runs bootstrap/registry work through `ensure_registry()`.
- Manual `just ingest`, `just bootstrap-bars`, and `just compute-indicators` recipes are useful but do not provide durable status, retry, holds, or rate-limit planning.
- Source rate limits exist in config and are partially enforced by the connector layer, but there is no first-class operator view of remaining budgets or safety overrides.
- Automated EOD refreshes need calendar-aware scheduling, idempotency, and failure visibility.

## Design Principles

1. **Data jobs only.** Jobs may ingest, import, validate, compute, reconcile, compact, or report lake facts. They must not contain strategy, ranking, allocation, buy/sell, or portfolio semantics.
2. **Flows remain the business logic.** Worker handlers are thin wrappers around `src/alpha_lake/flows/`.
3. **Durable, observable, idempotent.** Every worker run has a persisted row before execution, a terminal outcome, and an idempotency key.
4. **No heavy work in HTTP handlers.** API endpoints return current state or update job configuration. They do not run ingestion inline.
5. **No heavy work in server startup.** Startup may verify metadata tables exist, but must not bootstrap bars or compute indicators.
6. **Source behavior remains data.** Default rate limits, parser versions, enablement, and dataset-source mappings remain in `config/stack.toml` and the source registry. Runtime overrides are operational safety controls layered on top.
7. **Calendar-aware schedules.** EOD jobs use the pinned trading calendar and exchange session dates. They do not infer sessions from UTC calendar dates.
8. **Replay invariants still apply.** Worker execution must archive raw inputs, record manifests, preserve `available_at`, and never use wall-clock time inside canonical/replay paths except where an existing non-replay flow explicitly documents that exception.

## Non-Goals

- No arbitrary public API for adding or deleting job definitions.
- No strategy execution.
- No portfolio/order/book/actor command model.
- No distributed queue dependency such as Redis, RabbitMQ, or Celery in v1.
- No Dagster requirement. Dagster may later enqueue the same job definitions, but it must remain a shell over `flows/`.
- No write-time adjusted prices.

## Runtime Shape

Add one service to `compose.yaml`:

```yaml
worker:
  build:
    context: .
    dockerfile: Dockerfile
  command: ["worker", "--poll-interval", "5"]
  environment:
    ALPHA_LAKE_CONFIG: /config/stack.toml
    ALPHA_LAKE_DASHBOARD_ENABLED: "true"
    # same source API-key environment as app
  volumes:
    - ./config:/config:ro
    - ./data:/data
    - ~/Downloads:/downloads:ro
  depends_on:
    postgres:
      condition: service_healthy
    rustfs:
      condition: service_healthy
  entrypoint: ["alpha-lake"]
```

Recommended `just` additions:

```make
worker:
    docker compose run --rm app worker

jobs:
    docker compose run --rm app jobs
```

`just up` may continue to start only infrastructure, or it may start `postgres rustfs app worker` once the worker is stable. During rollout, prefer explicit `just worker` / `docker compose up -d worker`.

## Storage Model

Use Postgres for worker control tables. Do not store the job ledger in DuckLake canonical tables. Reasons:

- worker tables are operational metadata, not market facts;
- row locking with `FOR UPDATE SKIP LOCKED` is the simplest safe claim mechanism;
- the operational ledger should be queryable even if DuckLake attach fails;
- it avoids abusing canonical data retention/replay paths for process state.

The existing Postgres database is already present as the DuckLake catalog. Create a separate schema:

```sql
CREATE SCHEMA IF NOT EXISTS ops;
```

### `ops.job_definition`

Configured job templates. These are seeded by migration/config, not created ad hoc through the API.

```sql
CREATE TABLE ops.job_definition (
    job_name TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    hold BOOLEAN NOT NULL DEFAULT FALSE,
    schedule_kind TEXT NOT NULL,
    schedule_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    params_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    priority INTEGER NOT NULL DEFAULT 100,
    concurrency_key TEXT NOT NULL,
    source_id TEXT,
    dataset TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
```

`schedule_kind` values:

- `manual`: never auto-enqueued; can be run by CLI only.
- `interval`: enqueue after `schedule_json.interval_seconds`.
- `daily_time`: enqueue at local time in `schedule_json.time`, timezone in `schedule_json.timezone`.
- `market_close`: enqueue after a configured exchange session close offset.

Example `schedule_json`:

```json
{
  "timezone": "America/New_York",
  "time": "17:30",
  "calendar": "XNYS",
  "skip_non_trading_days": true
}
```

### `ops.job_run`

Durable run ledger. The scheduler inserts rows; the worker claims rows.

```sql
CREATE TABLE ops.job_run (
    run_id UUID PRIMARY KEY,
    job_name TEXT NOT NULL REFERENCES ops.job_definition(job_name),
    job_type TEXT NOT NULL,
    status TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    params_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    requested_for_date DATE,
    source_id TEXT,
    dataset TEXT,
    priority INTEGER NOT NULL DEFAULT 100,
    attempt INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    scheduled_at TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    heartbeat_at TIMESTAMPTZ,
    worker_id TEXT,
    result_json JSONB,
    failure_json JSONB,
    ingestion_run_id TEXT,
    ducklake_snapshot_id TEXT,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE UNIQUE INDEX ux_job_run_idempotency
    ON ops.job_run (job_name, idempotency_key);

CREATE INDEX ix_job_run_status_scheduled
    ON ops.job_run (status, scheduled_at, priority);
```

Allowed `status` values:

- `queued`
- `running`
- `succeeded`
- `failed`
- `cancelled`
- `deferred`
- `quota_exhausted`

Use plain `TEXT` values at first to avoid enum migration friction.

### `ops.source_rate_limit_override`

Runtime safety overrides. These only lower or hold configured source budgets unless an explicit `allow_raise` config flag is added later.

```sql
CREATE TABLE ops.source_rate_limit_override (
    source_id TEXT PRIMARY KEY,
    hold BOOLEAN NOT NULL DEFAULT FALSE,
    rate_limit_per_sec DOUBLE PRECISION,
    rate_limit_per_min INTEGER,
    rate_limit_per_day INTEGER,
    reason TEXT NOT NULL DEFAULT '',
    updated_by TEXT NOT NULL DEFAULT 'operator',
    updated_at TIMESTAMPTZ NOT NULL
);
```

Semantics:

- `hold=true` prevents the scheduler/worker from starting jobs that require the source.
- `NULL` means use configured value.
- Non-null values replace configured values for runtime checks.
- v1 should reject overrides that are higher than `config/stack.toml` unless an environment flag explicitly permits it.

### `ops.source_call_ledger`

Replace or augment the current file-backed call ledger with a Postgres-backed ledger for worker/app consistency.

```sql
CREATE TABLE ops.source_call_ledger (
    call_id UUID PRIMARY KEY,
    source_id TEXT NOT NULL,
    endpoint TEXT NOT NULL DEFAULT '',
    job_run_id UUID,
    called_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL,
    cost_units INTEGER NOT NULL DEFAULT 1,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX ix_source_call_ledger_source_called
    ON ops.source_call_ledger (source_id, called_at);
```

This table lets the API report calls in the last minute/day and lets the worker reserve budget across processes.

### `ops.worker_state`

Optional but useful for UI and stale-run detection:

```sql
CREATE TABLE ops.worker_state (
    worker_id TEXT PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    heartbeat_at TIMESTAMPTZ NOT NULL,
    current_run_id UUID,
    version TEXT NOT NULL DEFAULT ''
);
```

## Seeded Job Definitions

Implement these initial definitions:

| Job name | Type | Default schedule | Purpose |
|---|---|---:|---|
| `stooq.rebuild` | `stooq_rebuild` | manual | Rebuild local Parquet from the mounted STOOQ zip. |
| `bars.bootstrap.active` | `bars_bootstrap` | manual | Backfill active symbols from bulk STOOQ data. |
| `bars.refresh.eod` | `bars_refresh` | market close + 30m | Refresh configured active symbols from primary bars source. |
| `indicators.compute.eod` | `indicators_compute` | after `bars.refresh.eod` succeeds | Compute neutral technical facts after new bars arrive. |
| `datasets.refresh.core` | `dataset_refresh` | daily time | Refresh enabled core non-bars datasets. |
| `source.health` | `source_health` | interval | Probe configured source status and budgets without canonical writes. |

Do not seed experimental text datasets unless their dataset posture is enabled and explicitly configured.

## Job Handlers

Create `src/alpha_lake/jobs/`:

```text
src/alpha_lake/jobs/
  __init__.py
  models.py          # dataclasses / pydantic models for job rows
  store.py           # Postgres operational store
  scheduler.py       # due-job calculation and enqueue
  worker.py          # claim loop and dispatch
  handlers.py        # job_type -> handler
  rate_limits.py     # runtime override + call ledger helpers
```

Handlers must be thin:

```python
HANDLERS = {
    "stooq_rebuild": handle_stooq_rebuild,
    "bars_bootstrap": handle_bars_bootstrap,
    "bars_refresh": handle_bars_refresh,
    "indicators_compute": handle_indicators_compute,
    "dataset_refresh": handle_dataset_refresh,
    "source_health": handle_source_health,
}
```

Handler guidance:

- Open a fresh catalog connection per run.
- Validate params before doing work.
- Write raw/archive/manifest through existing ingestion paths.
- Return small `result_json` summaries such as row counts, symbol counts, skipped counts, and source budget state.
- Do not return market observations as job results except operational counts and identifiers.
- On `BudgetExhaustedError`, mark the run `quota_exhausted` or `deferred` with a retry time.

### `bars_refresh`

Expected params:

```json
{
  "symbols": "active",
  "from_policy": "last_missing_or_previous_session",
  "to_policy": "latest_closed_session",
  "source_id": null
}
```

Behavior:

1. Resolve active symbols from the symbol registry.
2. Resolve the latest closed exchange session with the pinned calendar.
3. For each symbol, compute missing dates before calling the source.
4. Use source precedence if `source_id` is null.
5. Stop before exceeding source budget; defer remaining symbols.
6. Persist `ingestion_run_id` and snapshot mapping in the existing ingestion flow.

### `bars_bootstrap`

Expected params:

```json
{
  "symbols": "active",
  "source_id": "stooq",
  "lookback_years": 3
}
```

Behavior:

1. Ensure local STOOQ Parquet exists or fail with a clear operator message.
2. Backfill only active symbols by default.
3. Avoid API calls.
4. Use idempotent coverage checks to skip existing bars.
5. Do not silently rewrite existing canonical rows.

Implementation note: the current bootstrap path should be tightened before making this the primary worker path. In particular, preserve raw/import manifest information and avoid unreviewed wall-clock use in canonical rows.

### `indicators_compute`

Expected params:

```json
{
  "symbols": "active",
  "trigger": "after_bars_refresh"
}
```

Behavior:

1. Run after successful bars refresh or manual bootstrap.
2. Use current non-research compute behavior unless a replay-specific compute path is requested.
3. Keep all outputs neutral. Run the forbidden-token grep gate for changes under `src/alpha_lake/derived/`.

### `source_health`

Behavior:

1. Report configured sources, credential presence, hold state, runtime overrides, calls in recent windows, and next reset estimates.
2. Avoid connector calls where health can be derived from local config/ledger.
3. If a live probe is configured, account for it in the call ledger.

## Worker Loop

Pseudo-code:

```python
def worker(poll_interval: float = 5.0, once: bool = False) -> None:
    load_config()
    store = JobStore.from_env()
    worker_id = build_worker_id()
    store.upsert_worker_state(worker_id)

    while True:
        store.heartbeat(worker_id)
        scheduler.enqueue_due_jobs(now=utc_now())
        run = store.claim_next(worker_id)
        if run is None:
            if once:
                return
            sleep(poll_interval)
            continue

        try:
            result = dispatch(run)
        except BudgetExhaustedError as exc:
            store.defer_or_quota_exhausted(run.run_id, exc)
        except Exception as exc:
            store.fail_or_retry(run.run_id, exc)
        else:
            store.succeed(run.run_id, result)
```

Claim query:

```sql
UPDATE ops.job_run
SET status = 'running',
    started_at = now(),
    heartbeat_at = now(),
    worker_id = %(worker_id)s,
    attempt = attempt + 1
WHERE run_id = (
    SELECT r.run_id
    FROM ops.job_run r
    JOIN ops.job_definition d ON d.job_name = r.job_name
    LEFT JOIN ops.source_rate_limit_override o ON o.source_id = r.source_id
    WHERE r.status IN ('queued', 'deferred')
      AND r.scheduled_at <= now()
      AND d.enabled = true
      AND d.hold = false
      AND COALESCE(o.hold, false) = false
    ORDER BY r.priority ASC, r.scheduled_at ASC
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
RETURNING *;
```

Concurrency:

- v1 may run a single worker process with one active job at a time.
- The schema supports multiple workers later.
- Use `concurrency_key` to prevent two runs that write the same dataset/source family concurrently.
- For DuckLake writes, default to conservative single-writer behavior until write-concurrency tests prove otherwise.

Retries:

- Transient failures retry with exponential backoff until `max_attempts`.
- Validation failures should fail terminally.
- Quota exhaustion should defer to the next safe window, not burn attempts.
- Every failure stores type, message, and small context in `failure_json`.

Stale runs:

- A run is stale when `status='running'` and `heartbeat_at` is older than a configured timeout.
- A CLI command may requeue stale runs.
- Do not automatically requeue a run that may still be writing canonical data unless the handler is proven idempotent.

## Scheduler

The scheduler is a small library called by the worker loop. It is not a separate service in v1.

Responsibilities:

1. Read enabled job definitions.
2. Skip held definitions and held sources.
3. Calculate due runs using UTC instants and pinned calendar rules.
4. Insert `ops.job_run` with deterministic idempotency keys.
5. Ignore duplicate-key conflicts.

Idempotency key examples:

- `bars.refresh.eod:2026-06-26:XNYS`
- `indicators.compute.eod:2026-06-26:after-bars-refresh`
- `source.health:2026-06-28T10:15Z`

For EOD jobs, `requested_for_date` must be the exchange session date, not the UTC date.

Dependency support:

- v1 can implement simple dependencies in `schedule_json`, e.g.:

```json
{
  "after_job": "bars.refresh.eod",
  "same_requested_for_date": true
}
```

- If dependency support is deferred, let `indicators.compute.eod` run on its own daily schedule and compute only when source data changed.

## API Surface

All endpoints require the existing API-key auth. These endpoints are operational controls. They should be namespaced under `/v1/ops`.

### Job definitions

#### `GET /v1/ops/jobs`

List configured job definitions and current state.

Response fields:

- `job_name`
- `job_type`
- `enabled`
- `hold`
- `schedule_kind`
- `schedule`
- `source_id`
- `dataset`
- `last_run`
- `next_due_at`
- `last_status`

#### `GET /v1/ops/jobs/{job_name}`

Return one job definition with recent run history.

#### `PATCH /v1/ops/jobs/{job_name}`

Allowed changes only:

- `enabled`
- `hold`
- `schedule_json`
- `max_attempts`
- `priority`

Disallowed changes:

- `job_name`
- `job_type`
- arbitrary params that change what data is owned by the job
- creating new jobs
- deleting jobs

Example request:

```json
{
  "hold": true,
  "reason": "pause EOD refresh during provider incident"
}
```

Example schedule update:

```json
{
  "schedule_json": {
    "timezone": "America/New_York",
    "time": "18:15",
    "calendar": "XNYS",
    "skip_non_trading_days": true
  }
}
```

### Job runs

#### `GET /v1/ops/job-runs`

Query recent runs.

Query params:

- `status`
- `job_name`
- `source_id`
- `dataset`
- `limit`

#### `GET /v1/ops/job-runs/{run_id}`

Return one run with result/failure detail.

#### `POST /v1/ops/job-runs/{run_id}/cancel`

Allowed only when status is `queued` or `deferred`. For `running`, v1 should return `409` and explain that running jobs cannot be killed safely.

#### `POST /v1/ops/job-runs/{run_id}/requeue`

Allowed only for terminal `failed`, `quota_exhausted`, or stale operator-reviewed runs. Creates a new run with a derived idempotency key suffix such as `:retry:1`. Do not mutate terminal history.

### Source budgets

#### `GET /v1/ops/sources`

List sources with configured limits, runtime overrides, hold state, and recent call counts.

Response fields:

- `source_id`
- `requires_key`
- `has_key`
- `configured_rate_limit_per_sec`
- `configured_rate_limit_per_min`
- `configured_rate_limit_per_day`
- `effective_rate_limit_per_sec`
- `effective_rate_limit_per_min`
- `effective_rate_limit_per_day`
- `hold`
- `calls_last_min`
- `calls_last_day`
- `next_day_reset_at`

#### `GET /v1/ops/sources/{source_id}`

Return one source plus recent calls and jobs waiting on that source.

#### `PATCH /v1/ops/sources/{source_id}/rate-limit`

Allowed changes:

- `hold`
- `rate_limit_per_sec`
- `rate_limit_per_min`
- `rate_limit_per_day`
- `reason`

Safety rules:

- Empty fields leave current override unchanged.
- `null` clears the override for that field.
- Values higher than configured limits are rejected by default.
- Setting `hold=true` should not cancel a running job; it prevents new claims.

Example:

```json
{
  "hold": true,
  "reason": "Alpha Vantage daily quota nearly exhausted"
}
```

### Worker state

#### `GET /v1/ops/workers`

Return worker heartbeat, current run, and stale status.

No endpoint is required to add workers. Workers are created by starting containers.

## CLI Surface

Add commands:

```text
alpha-lake worker --poll-interval 5 --once
alpha-lake jobs list
alpha-lake jobs runs --status failed --limit 20
alpha-lake jobs hold bars.refresh.eod --reason "provider incident"
alpha-lake jobs resume bars.refresh.eod
alpha-lake sources limits
alpha-lake sources hold alphav --reason "quota protection"
alpha-lake sources set-limit tiingo --per-min 20
```

The CLI may include a manual run command for trusted operators:

```text
alpha-lake jobs enqueue bars.bootstrap.active --reason "initial lake load"
```

This is acceptable because the user specifically asked not to expose public API endpoints to add/remove jobs. A local CLI command for seeded definitions is useful for bootstrap and recovery.

## Config

Add an optional `[worker]` section to `config/stack.toml`:

```toml
[worker]
enabled = true
poll_interval_seconds = 5
stale_after_seconds = 900
allow_rate_limit_raise = false
max_active_runs = 1

[worker.jobs.bars_refresh_eod]
enabled = true
hold = false
job_name = "bars.refresh.eod"
job_type = "bars_refresh"
schedule_kind = "market_close"
concurrency_key = "bars"
source_id = "auto"
dataset = "bars"
max_attempts = 3
priority = 10
schedule = { calendar = "XNYS", offset_minutes = 30 }
params = { symbols = "active", source_id = "auto" }
```

Implementation options:

1. Seed `ops.job_definition` from config on startup/worker startup.
2. Migrations create default rows, and config only overrides them.

Prefer option 1. It keeps job definitions declarative and reviewable. Runtime API changes update the database only; they are safety overrides until the config is changed.

## Rate-Limit Enforcement

Current connector budget tracking is process/file-backed. The worker needs process-shared budgets because both `app` and `worker` can call connectors.

Implementation path:

1. Add `jobs/rate_limits.py` that reads source config plus `ops.source_rate_limit_override`.
2. Before any connector call, reserve a call in `ops.source_call_ledger` in a short transaction.
3. Count calls within second/minute/day windows using Postgres.
4. If the call would exceed budget, raise `BudgetExhaustedError`.
5. Record final status after the call completes.

For v1, it is acceptable to leave existing connector checks in place and add worker-level preflight checks. The long-term target is one shared limiter used by all connector calls.

Daily reset policy:

- Store timestamps in UTC.
- For sources with known reset zones, calculate display/reset guidance in the API response.
- Do not erase ledger rows at reset; filter by window.

## Symbol Registry Implications

The current symbol registry should become durable operational metadata. Avoid an in-memory DuckDB-only registry for worker scheduling.

Recommended path:

1. Move active/removed symbol registry storage into Postgres `ops.symbol_registry`, or into a persistent operational table with equivalent durability.
2. Keep canonical market facts immutable; symbol registry changes are operational inclusion/exclusion controls.
3. `DELETE /v1/symbols/{symbol}` should continue to soft-remove only. Data stays in the lake.
4. `POST /v1/symbols` should update registry and enqueue/allow the relevant configured bootstrap job. It should not perform long-running backfill inline.

If symbol registry migration is too large for the first worker PR, implement worker storage first and leave a follow-up issue. Do not start large automated jobs from an in-memory registry.

## Startup Changes

Change FastAPI startup behavior:

- Keep cheap checks: config load, kernel registration, metadata table existence check.
- Remove or gate heavy `ensure_registry()` work from app lifespan.
- If bootstrap is needed, enqueue or document `bars.bootstrap.active`.

Suggested environment flag during transition:

```text
ALPHA_LAKE_STARTUP_BOOTSTRAP=false
```

Default should become `false`.

## Security and Audit

- Reuse existing API-key auth for `/v1/ops/*`.
- Include a simple `updated_by` field from API key label or request header where available.
- Store `reason` for holds, resumes, schedule changes, and rate-limit overrides.
- Do not log API keys, raw payloads, or secrets.
- Do not expose source API keys in `/v1/ops/sources`.

## Observability

Use structured logs for:

- `job.queued`
- `job.claimed`
- `job.succeeded`
- `job.failed`
- `job.deferred`
- `job.quota_exhausted`
- `source.hold.changed`
- `job_definition.changed`

Each log should include:

- `run_id`
- `job_name`
- `job_type`
- `source_id`
- `dataset`
- `worker_id`
- `attempt`
- row counts where applicable
- duration

Add health output:

- worker table migration present,
- count of queued/running/failed jobs,
- stale worker count,
- held job/source count.

## Testing Requirements

Unit tests:

- scheduler creates one due run and ignores duplicate idempotency key,
- held job definition is not enqueued,
- held source prevents claim,
- rate-limit override lower than config is enforced,
- attempted rate-limit raise is rejected by default,
- failed transient run is retried with later `scheduled_at`,
- quota exhaustion defers without consuming attempts,
- `PATCH /v1/ops/jobs/{job_name}` rejects job type/name changes,
- `PATCH /v1/ops/sources/{source_id}/rate-limit` never returns secrets.

Integration tests:

- worker `--once` claims and completes a seeded `source_health` run,
- `bars_bootstrap` skips already-covered rows,
- `bars_refresh` narrows missing dates before connector calls,
- running job appears in `/v1/ops/job-runs`,
- API can hold and resume a job definition,
- source hold prevents new work but does not mutate existing terminal runs.

Replay/invariant tests:

- Worker-triggered ingestion produces the same canonical facts as the CLI path for the same raw inputs.
- Worker retries do not duplicate canonical rows when a run is requeued.
- No source API call is made for fully-covered historical date ranges.
- No forbidden strategy tokens are introduced under `src/alpha_lake/derived/`.

## Rollout Plan

### Phase 1: Operational Store and Read-Only API

- Add `ops` schema migration helpers.
- Add `JobStore`.
- Seed job definitions from config.
- Add read-only `/v1/ops/jobs`, `/v1/ops/job-runs`, `/v1/ops/sources`, `/v1/ops/workers`.
- Add CLI list commands.
- No worker execution yet.

### Phase 2: Worker Loop and Safe Handlers

- Add `alpha-lake worker`.
- Implement `source_health`, `stooq_rebuild`, and `indicators_compute`.
- Add Compose worker service.
- Add structured logs and health output.

### Phase 3: Bars Bootstrap and Refresh

- Move heavy symbol-add backfill out of HTTP request path.
- Implement durable symbol registry or equivalent.
- Implement `bars_bootstrap` and `bars_refresh`.
- Ensure bootstrap/import path records the required manifest/provenance data.
- Add rate-limit-aware deferral.

### Phase 4: Operator Controls

- Add PATCH endpoints for job holds/schedules and source holds/limits.
- Add cancellation/requeue for safe states.
- Add dashboard panels if desired.

### Phase 5: Startup Cleanup

- Disable heavy startup bootstrap by default.
- Document worker-first operational flow in `docs/operations.md`.
- Update `docs/serving-api.md` for changed symbol endpoint behavior.

## Acceptance Criteria

- `alpha-lake worker --once` can claim and complete a queued seeded job.
- `/v1/ops/jobs` shows configured jobs, hold state, schedule, last run, and next due time.
- `/v1/ops/job-runs` shows queued/running/terminal runs.
- `/v1/ops/sources` shows configured limits, effective limits, holds, and recent call counts without exposing secrets.
- Operators can hold/resume a configured job and lower/clear source limits through API.
- API cannot create/delete arbitrary job definitions.
- `POST /v1/symbols` no longer performs long-running backfill inline after the worker-backed path is enabled.
- Worker execution uses existing `flows/` functions rather than duplicating pipeline logic.
- Fully-covered historical ranges do not trigger source API calls.
- Running worker and API together share source budget state.
- All changes preserve Alpha-Lake invariants and pass `just lint`, relevant tests, and the forbidden-token grep when derived code is touched.

## Implementation Notes for OpenCode

- Start by adding the store and read-only surfaces. Avoid touching ingestion semantics in the first PR.
- Prefer small PRs by phase. The bars bootstrap path needs extra care because it affects canonical market facts.
- Use `psycopg2` or a tiny direct Postgres adapter already available in the project dependencies. Do not add SQLAlchemy unless there is a strong reason.
- Keep migrations simple and idempotent. If there is no migration framework yet for operational tables, add a small `ensure_ops_schema()` function called by worker startup and health checks.
- Keep all handler params explicit and validated with Pydantic models.
- Keep job results operational: counts, statuses, identifiers, timings. Do not include strategy-like interpretations of market data.
- When changing source rate-limit behavior, update `docs/api-keys.md` and `docs/production.md`.
- When changing symbol endpoint behavior, update `docs/serving-api.md` and `docs/operations.md`.
