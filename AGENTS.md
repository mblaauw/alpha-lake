# AGENTS.md — Alpha-Lake

Always-on rules for every OpenCode session in this repo. Keep this file small; it is in
context on **every** turn. Detail lives in skills (pull) and `@`-referenced files (lazy).

## How to use this file

- The rules under **Invariants** and **Forbidden** are mandatory on every task. They override defaults.
- The **Skill index** tells you which skill to load for which task. Load it before writing code of that kind.
- A `@path` reference (e.g. `@docs/DESIGN.md`) is **lazy**: read it with your Read tool only when the
  current task needs it. Do **not** preemptively load all references.

## Project snapshot

Alpha-Lake is a stack-first, tri-temporal, replayable **market-data lakehouse**. It ingests, archives,
validates, and serves **point-in-time-correct** market facts. It owns facts; it knows nothing about strategy.

Stack: Python 3.13+ · uv · DuckLake 1.0 extension (Parquet + SQL catalog) · Postgres catalog · RustFS (S3) ·
httpx connectors · Polars + Patito (model = schema = validator) · DuckDB engine · Typer CLI · Docker Compose ·
FastAPI / Uvicorn server · Lake Watch dashboard · Dagster (optional).

Secrets via `SecretStore` ABC (`EnvSecretStore` / `StaticSecretStore`); see `@src/alpha_lake/secrets.py`.

Full spec: `@docs/DESIGN.md`. Operations: `@docs/operations.md`. Decisions: `@docs/adr/`.

## Workflow

- **Every issue requires a PR before closing.** No issue moves to Done without an associated pull request.
  PRs must link to the issue they resolve (e.g. `Closes #N` in the description).
- **Each epic closes with a cross-functional refinement gate** before the next epic starts.
  Gate checklists live in `@docs/gates/`. Load the relevant gate document and tick items
  as part of the epic-closing PR.
- **Review → Done lifecycle:** After closing an issue via PR, set its status on the project board to
  "Review". Periodically (or before closing an epic), check each "Review" issue's acceptance criteria
  against the code. If all ACs are met, move the issue to "Done". This should be part of every
  epic-closing PR.
- **When closing any issue, always check the full project board** for other closed issues not yet in
  "Review"/"Done" status — not just issues from the current epic. Use:
  ```bash
  gh issue list --state closed --limit 200 --json number,projectItems -q "." | python3 -c "
  import sys,json
  for i in json.load(sys.stdin):
      items = i.get('projectItems') or [{}]
      s = items[0].get('status',{}).get('name','')
      if s not in ('Review','Done',''): print(f'#{i[\"number\"]}: {s}')
  "
  ```

## Command surface

Use these; do not invent commands and do not install Postgres / RustFS / DuckDB on the host.

```
just up | down | reset | logs        # reference stack lifecycle
just bootstrap | ingest | health     # operate the lake
just serve                           # start FastAPI server + dashboard on :8000
just test *[path]                    # unit + integration (embedded)
just test-integration *[path]        # live API tests (--run-live)
just replay *[path]                  # golden replay (tests/replay/)
just freeze-fixtures                 # freeze golden replay fixtures
just lint                            # ruff + ty + import-linter
just vendor                          # offline wheelhouse + images (online step)
```

**Running CLI commands against the stack.** The `app` Compose service runs the FastAPI server
by default. For one-off CLI commands (ingestion, bootstrap, dataset, health), use:

```
docker compose run --rm app <subcommand> [args]
```

To start the server (also started by `just up + compose.yaml`):

```
just serve
# or: docker compose run --rm --service-ports app serve
```

**Config changes require rebuild.** When you modify `config/stack.toml` or `src/` files, run
`docker compose build app` before `just up` so the container picks up the changes.

Air-gap: `just vendor` online → copy `vendor/` → `just up` (no network at runtime).

## Invariants — mandatory, every turn

1. **No strategy semantics, anywhere.** The lake emits neutral measurements only. Never produce scores,
   ranks, signals, or buy/sell/bullish/bearish judgments. (I3 / §14.5 / §15.5)
2. **Research reads require explicit `as_of`.** Never default to "latest." A read with no `as_of` must fail
   loudly, not silently return newest. `latest_*` is a separate, clearly non-research path. (I5, I12)
3. **Raw is immutable; corrections are new versions.** Never rewrite or delete raw, manifests, or canonical
   rows. A correction mints a new `available_at` version. (I1, I4)
4. **Never use wall-clock in the canonical or replay path.** Use the recorded `available_at` from the
   manifest. `now()` in canonicalize/replay is a bug. (I7)
5. **Determinism is non-negotiable.** `security_id` and all version/content hashes are pure functions of
   stable inputs — sorted keys, UTC timestamps, pinned float repr, fixed `normalization_version`. No
   randomness, no map-ordering dependence, in any path that golden replay covers.
6. **Adjusted prices are read-time and PIT-bounded.** Apply only corp actions with
   `available_at <= as_of`. Adjusted prices are never stored. (I6)
7. **Dates use the pinned trading calendar; instants are UTC.** `effective_date` is the exchange-session
   date. Do not invent date logic; resolve via the calendar oracle.

## Forbidden tokens (grep gate)

No identifier, column, function, or output anywhere under `src/alpha_lake/derived/` may contain strategy semantics. Before committing changes to those paths, run:

```
rg -i -n 'signal|bullish|bearish|\brank\b|\bscore\b|\bbuy\b|\bsell\b|golden_cross|hype|candidate|portfolio_weight|stop_loss|trade_decision' src/alpha_lake/derived
```

A hit is a stop-and-fix, not a warning. Neutral names only (`mean_sentiment`, `sma`, `mention_count`).

## Definition of done (any code change)

- `just lint` clean (ruff + ty + import-linter).
- Forbidden-token grep clean.
- New dataset or reader ships leakage, restatement, and idempotency tests (see `golden-replay` skill).
- PR created with `Closes #N` linking to the issue.

## Skill index — load the right one before you start

| Task | Load skill |
|---|---|
| Anything touching invariants / before committing | `alpha-lake-invariants` |
| Running the stack, uv, air-gap, container commands | `stack-ops` |
| Adding a new dataset end-to-end (the vertical slice) | `add-dataset` (pulls `connector`, `patito-fact`, `pit-reader`, `serving-kernel`) |
| Working with the SQL kernel / PIT macros / register_kernel | `serving-kernel` |
| Modifying the REST transport, auth, rate limiting, endpoints | `rest-transport` |
| Writing a connector / fetch + raw archive | `connector` |
| Writing a fact model / validation gate | `patito-fact` |
| Writing an `as_of` reader or panel/asof-join | `pit-reader` |
| Fixtures, replay, property tests, determinism | `golden-replay` |
| Defining or changing a dataset contract | `dataset-contract` |

If a task spans several rows, load `add-dataset` first — it orchestrates the others.

## Model routing — these tasks need extra care

The following are invariant-dense and easy to get subtly wrong. Prefer a stronger model, work in small
steps, and always gate behind property tests + cross-check with the `alpha-lake-invariants` skill. If unsure, stop and ask rather than guess:

- the PIT reader / `ASOF JOIN` knowledge-time resolution,
- deterministic `security_id` minting,
- the semantic `version_hash` recipe,
- golden-replay determinism (business output **and** bitemporal row visibility),
- storage blob-store backend selection (`_LocalBlobStore` vs `_S3BlobStore`) and the `get_blob_store()` factory,
- Patito-derived DDL generation (`_generate_ddl()` schema ↔ database sync) and the `Dataset`/`DATASETS` registry,
- serving-kernel SQL macro precedence resolution (`_kernel_source_priority`, `COALESCE(priority, 999)` pattern),
- REST transport lookback cap, auth, and rate-limiting invariants,

## Product posture

News and social datasets are **experimental** (tier 3), disabled by default, and not SLA-eligible.
Do not add or expand text connectors unless explicitly requested and the dataset config posture is
updated first. Deepen core facts (bars, fundamentals, corp actions, reconciliation) instead.

## Conventions

- One dataframe lib (Polars) and one SQL engine (DuckDB) — never both for the same job.
- Pipeline logic lives once in `flows/`; CLI / tests / Dagster are thin shells over it. Do not duplicate logic.
- Secrets come from env (`*_env` names in the registry); never write secrets to raw, canonical, manifests,
  logs, fixtures, or snapshots.
- Source behavior (rate limit, retry, precedence, freshness, parser/contract version) is **data** in the
  registry, not hardcoded.
