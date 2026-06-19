# Alpha-Lake

Stack-first, bitemporal market-data lakehouse. Ingests, archives, validates, and serves point-in-time-correct market facts to notebooks, backtests, dashboards, ML, and trading systems.

> **Owns facts. Serves what was knowable as of a date. Knows nothing about strategy.**

## Quick start

```bash
just up        # start the reference stack (Postgres + RustFS + app)
just bootstrap # initialize the catalog
just ingest    # ingest market data
just health    # check dataset freshness and status
```

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

## Build plan (9 epics)

| Epic | Phase | Focus | Priority |
|------|-------|-------|----------|
| Epic 0 | Phase 0 | Foundation: stack, CI, OTel, config | P0 |
| Epic 1 | Phase 1 | Bars vertical slice: connector → PIT read | P0 |
| Epic 2 | Phase 2 | Testing: replay harness, fixtures, contract tests | P0 |
| Epic 3 | Phase 3 | Identity: security master, corp actions, adjusted views | P1 |
| Epic 4 | Phase 4 | Remaining datasets: fundamentals, insider, news, social/text analytics | P1 |
| Epic 5 | Phase 5 | Serving: panel, PIT joins, catalog, health, latest_* | P1 |
| Epic 6 | Phase 6 | Orchestration: Dagster, CLI parity, gap-fill, backfill | P1 |
| Epic 7 | Phase 7 | Packaging: vendor, air-gap, Nix, release workflow | P2 |
| Epic 8 | Phase 8 | Hardening: contracts, SQLMesh, Arrow Flight, K8s | P2 |

Each epic closes with a cross-functional refinement gate (Dev, PO, Architect, UX, Systems Designer, Data Architect, Data Engineer) before the next epic begins.

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

## Architecture Decision Records

| ADR | Title | Status |
|-----|-------|--------|
| 0001 | DuckLake as lakehouse format and catalog | Proposed |
| 0002 | Tri-temporal tracking model | Proposed |
| 0003 | SCD2 on knowledge time boundary | Proposed |
| 0004 | Deterministic replay via content-addressed archive | Proposed |
| 0005 | Security master PIT resolution | Proposed |
| 0006 | Read-time adjusted price computation | Proposed |
| 0007 | Embedded SQLite/local-fs harness for testing | Proposed |
| 0008 | dlt for ingestion framework with idempotency | Proposed |
| 0009 | Fact store + transform library, never a feature store | Proposed |
| 0010 | Flow functions; Typer CLI first, Dagster optional later | Proposed |
| 0011 | OpenTelemetry OTLP collector in stack, console in harness | Proposed |
| 0012 | Stack-first Compose; all deps vendored in-repo | Proposed |
| 0013 | Nix flake as hermetic reproducibility ceiling | Proposed |
| 0014 | Source registry as data; precedence/freshness not hardcoded | Proposed |
| 0015 | Embedded mode demoted to test/debug/golden-replay harness | Proposed |
| 0016 | Kubernetes is future target, not v0.1 development substrate | Proposed |
| 0017 | Derived technical indicator library | Accepted |
| 0018 | Derived news & social analytics layer | Accepted |

## License

Apache 2.0
