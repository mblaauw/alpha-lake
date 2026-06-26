---
name: stack-ops
description: Alpha-Lake stack commands, uv/just/Docker workflow, and air-gap operations. Use when running tools, containers, tests, lint, ingestion, health, or dependency commands.
---

# Stack Ops

Use the project command surface. Do not invent host-side service commands.

## Decision Table

| Task | Command |
|---|---|
| Lint + type check + format check | `just lint` |
| Unit/integration tests | `just test` |
| Replay tests | `just replay` |
| Freeze golden fixtures | `just freeze-fixtures` |
| Compute indicators | `just compute-indicators` |
| Start stack | `just up` |
| Stop stack | `just down` |
| Reset stack | `just reset` |
| Logs | `just logs` |
| Rebuild app image after code/config changes | `just build` |
| Add runtime dep | `uv add <pkg>` |
| Add dev dep | `uv add --dev <pkg>` |
| Lock deps | `uv lock` |

## Tool Rules

- Always run Python tools through `uv run` when not using `just`.
- Never run bare `ruff`, `ty`, or `pytest` unless diagnosing a missing `uv` problem.
- Never run `ruff format`; opencode formatter handles formatting.
- Commit `uv.lock` after dependency changes.
- Docker uses `uv sync --frozen`; stale lock files break builds.

## App Container Pattern

Until the app service has a long-lived command, prefer one-shot execution:

```bash
docker compose run --rm app alpha-lake health
docker compose run --rm app alpha-lake bootstrap
docker compose run --rm app alpha-lake ingest bars --source eodhd
```

Do not assume `docker compose exec app ...` works after `just up`; the app container may have exited.

## Air-Gap Flow

```bash
just vendor
just up --offline
```

The repo carries dependencies: `uv.lock`, `vendor/wheelhouse`, `vendor/images`, and optional `vendor/bin`.

## Pre-Commit Gate

```bash
just lint
```

If `just` is unavailable:

```bash
uv run ruff check src/ tests/
uv run ty check --output-format full
```

## Forbidden

- Do not install or require host Postgres, RustFS, or DuckDB extensions.
- Do not edit dependency lists by hand when `uv add` can do it.
- Do not use `docker compose exec app` in new docs or recipes until the app lifecycle issue is fixed.
