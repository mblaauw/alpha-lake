# Alpha-Lake

[![CI](https://github.com/mblaauw/alpha-lake/actions/workflows/ci.yaml/badge.svg)](https://github.com/mblaauw/alpha-lake/actions/workflows/ci.yaml)
[![Release](https://github.com/mblaauw/alpha-lake/actions/workflows/release.yaml/badge.svg)](https://github.com/mblaauw/alpha-lake/actions/workflows/release.yaml)
[![Python](https://img.shields.io/badge/python-3.13%20|%203.14-blue)](https://www.python.org)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)

Stack-first, bitemporal market-data lakehouse. Ingests, archives, validates, and serves point-in-time-correct market facts to notebooks, backtests, dashboards, ML, and trading systems.

> **Owns facts. Serves what was knowable as of a date. Knows nothing about strategy.**

## Quick start

```bash
just up        # start the reference stack (Postgres + RustFS)
just bootstrap # initialize the catalog
just ingest    # ingest market data (synthetic by default — see below)
just health    # check dataset freshness and status
```

**`just ingest` produces synthetic bars by default.** No API keys are needed. The synthetic
pipeline generates deterministic market-data samples that pass all validation gates and
let you exercise the full ingest → PIT-read path. To ingest **live** market data, set the
corresponding `*_API_KEY` environment variables for your sources (see [Data suppliers](#datasets--data-suppliers))
and the connector is activated automatically. Only sources with configured API keys are
exercised end-to-end against real endpoints.

### Live ingestion

| Source | Env var |
|--------|---------|
| EODHD | `ALPHA_LAKE_EODHD_API_KEY` |
| Tiingo | `ALPHA_LAKE_TIINGO_API_KEY` |
| Alpaca | `ALPHA_LAKE_ALPACA_API_KEY` |
| Reddit | `ALPHA_LAKE_REDDIT_CLIENT_ID`, `ALPHA_LAKE_REDDIT_CLIENT_SECRET` |

## Datasets & data suppliers

| Dataset | Primary Source | Secondary Source(s) |
|---------|---------------|-------------------|
| OHLCV bars — daily | EODHD / Tiingo EOD | Alpaca |
| OHLCV bars — intraday | Alpaca (deferred) | Tiingo IEX, EODHD |
| Fundamentals | SEC EDGAR Companyfacts | Tiingo, EODHD |
| Insider transactions | SEC EDGAR Forms 3/4/5 | commercial (future) |
| Earnings calendar | EODHD | — |
| News articles | Tiingo News | Alpaca News, EODHD News |
| Social posts | Reddit API | Tiingo/EODHD enrichment |
| Corporate actions | EODHD / Tiingo splits-dividends | SEC filings (validation) |
| Security master | Alpha-Lake internal | OpenFIGI, EODHD, Tiingo, SEC |

## Completed epics

| Epic | Phase | Focus | Priority |
|------|-------|-------|----------|
| Epic 0 | Phase 0 | Foundation: stack, CI, config | P0 ✅ |
| Epic 1 | Phase 1 | Bars vertical slice: connector → PIT read | P0 ✅ |
| Epic 2 | Phase 2 | Testing: replay harness, fixtures, contract tests | P0 ✅ |
| Cleanup | — | Retrospective: timezone, SQL injection, dead code, test hygiene, import-linter, ClockPort | P0 ✅ |
| Cleanup 2 | — | Post-Epic-0-4: justfile fix, SEC endpoints, schema consistency, ty clean, docker pins | P0 ✅ |
| Epic 3 | Phase 3 | Identity: security master, corp actions, adjusted views | P1 ✅ |
| Epic 4 | Phase 4 | Remaining datasets: fundamentals, insider, news, social/text analytics | P1 ✅ |
| Epic 5 | Phase 5 | Serving: panel, PIT joins, catalog, health, latest_* | P1 ✅ |
| Epic 6 | Phase 6 | Orchestration: Dagster, CLI parity, gap-fill, backfill | P1 ✅ |
| Epic 7 | Phase 7 | Cloud-native hardening: secrets, snapshot pinning, observability, docs | P2 ✅ |
| Epic 300 | Storage Collapse | Unified blob store, Patito-derived DDL, mode-parity guard | P0 ✅ |

Each epic closes with a cross-functional refinement gate (Dev, PO, Architect, UX, Systems Designer, Data Architect, Data Engineer) before the next epic begins. Gate checklists are in [docs/gates/](docs/gates/).

## Project board

All work is tracked on the [Alpha-Lake Project Board](https://github.com/users/mblaauw/projects/4) with Status, Priority, Size, and Phase fields.

## Principles

- **Raw is immutable** — every payload archived verbatim before parsing
- **Point-in-time correctness** — no consumer sees future data
- **Tri-temporal** — valid time, knowledge time, system time tracked independently
- **Facts, not opinions** — neutral transforms only; strategy belongs to consumers
- **Stack-first** — Compose reference runtime from day one; embedded only for tests/replay
- **Decisions documented** — all architecture decisions recorded as ADRs in [docs/adr/](docs/adr/)

## Design

See [docs/DESIGN.md](docs/DESIGN.md) for the full systems design and implementation reference (v3.1).  
See [docs/operations.md](docs/operations.md) for operations guidance, memory sizing, and monitoring thresholds.

## Architecture Decision Records

| ADR | Title | Status |
|-----|-------|--------|
| 0001 | DuckLake as lakehouse format and catalog | Accepted |
| 0002 | Tri-temporal tracking model | Accepted |
| 0003 | SCD2 on knowledge time boundary | Accepted |
| 0004 | Deterministic replay via content-addressed archive | Accepted |
| 0005 | Security master PIT resolution | Accepted |
| 0006 | Read-time adjusted price computation | Accepted |
| 0007 | Embedded SQLite/local-fs harness for testing | Accepted |
| 0008 | dlt for ingestion framework with idempotency | Superseded |
| 0009 | Fact store + transform library, never a feature store | Refined by 0017 |
| 0010 | Flow functions; Typer CLI first, Dagster optional later | Accepted |
| 0011 | OpenTelemetry OTLP collector in stack, console in harness | Superseded |
| 0012 | Stack-first Compose; all deps vendored in-repo | Accepted |
| 0013 | Nix flake as hermetic reproducibility ceiling | Superseded by ADR-0012 |
| 0014 | Source registry as data; precedence/freshness not hardcoded | Accepted |
| 0015 | Embedded mode demoted to test/debug/golden-replay harness | Accepted |
| 0016 | Kubernetes is future target, not v0.1 development substrate | Accepted |
| 0017 | Derived technical indicator library | Accepted |
| 0018 | Derived news & social analytics layer | Accepted |
| 0019 | Polars + Patito for DataFrame processing and model validation | Accepted |
| 0020 | Trading calendar and timezone policy | Accepted |
| 0021 | Snapshot retention, compaction, and pinned reproducibility | Accepted |
| 0022 | Blob store — unified raw archive interface | Accepted |
| 0023 | Dataset descriptor for unified canonical write | Accepted |
| 0024 | SQL kernel macros over inline stored procedures | Accepted |
| 0025 | Dataset support tiers | Accepted |
| 0027 | Structured JSON logging replaces OpenTelemetry as default observability | Accepted |

## Development

### Workflow

- Every issue requires a PR before closing. No issue moves to Done without an associated pull request.
- PRs must link to the issue they resolve (e.g. `Closes #N`).

### opencode skills

Project-local skills live in `.opencode/skills/<name>/SKILL.md`. After creating or editing a skill, restart opencode to pick up the changes.

## License

Apache 2.0
