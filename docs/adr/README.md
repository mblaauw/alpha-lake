# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for Alpha-Lake.

Each ADR follows the [Michael Nygard template](https://github.com/joelparkerhenderson/architecture-decision-record/blob/main/templates/decision-record-template-michael-nygard/index.md).

## Active ADRs

| ADR | Title | Status |
|-----|-------|--------|
| 0001 | DuckLake as lakehouse format and catalog | Accepted |
| 0002 | Tri-temporal tracking model | Accepted |
| 0003 | SCD2 on knowledge time boundary | Accepted |
| 0004 | Deterministic replay via content-addressed archive | Accepted |
| 0005 | Security master PIT resolution | Accepted |
| 0006 | Read-time adjusted price computation | Accepted |
| 0007 | Embedded SQLite/local-fs harness for testing | Accepted |
| 0008 | dlt for ingestion framework with idempotency | Accepted |
| 0009 | Fact store + transform library, never a feature store | Refined by 0017 |
| 0010 | Flow functions; Typer CLI first, Dagster optional later | Accepted |
| 0011 | OpenTelemetry OTLP collector in stack, console in harness | Accepted |
| 0012 | Stack-first Compose; all deps vendored in-repo | Accepted |
| 0013 | Nix flake as hermetic reproducibility ceiling | Superseded |
| 0014 | Source registry as data; precedence/freshness not hardcoded | Accepted |
| 0015 | Embedded mode demoted to test/debug/golden-replay harness | Accepted |
| 0016 | Kubernetes is future target, not v0.1 development substrate | Accepted |
| 0017 | Derived technical indicator library (neutral, PIT-bounded, cacheable) | Accepted |
| 0018 | Derived news & social analytics layer (neutral, PIT-bounded, versioned) | Accepted |
| 0019 | Polars + Patito for DataFrame processing and model validation | Accepted |
| 0020 | Trading calendar and timezone policy | Accepted |
| 0021 | Snapshot retention, compaction, and pinned reproducibility | Accepted |
| 0022 | Blob store — unified raw archive interface | Accepted |
| 0023 | Dataset descriptor for unified canonical write | Accepted |
| 0024 | Serving architecture — versioned SQL kernel, REST transport, API key auth | Accepted |
