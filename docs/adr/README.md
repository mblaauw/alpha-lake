# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for Alpha-Lake.

Each ADR follows the [Michael Nygard template](https://github.com/joelparkerhenderson/architecture-decision-record/blob/main/templates/decision-record-template-michael-nygard/index.md).

## Active ADRs

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
| 0009 | Fact store + transform library, never a feature store | Refined by 0017 |
| 0010 | Flow functions; Typer CLI first, Dagster optional later | Proposed |
| 0011 | OpenTelemetry OTLP collector in stack, console in harness | Proposed |
| 0012 | Stack-first Compose; all deps vendored in-repo | Proposed |
| 0013 | Nix flake as hermetic reproducibility ceiling | Proposed |
| 0014 | Source registry as data; precedence/freshness not hardcoded | Proposed |
| 0015 | Embedded mode demoted to test/debug/golden-replay harness | Proposed |
| 0016 | Kubernetes is future target, not v0.1 development substrate | Proposed |
| 0017 | Derived technical indicator library (neutral, PIT-bounded, cacheable) | Accepted |
| 0018 | Derived news & social analytics layer (neutral, PIT-bounded, versioned) | Accepted |
| 0019 | Polars + Patito for DataFrame processing and model validation | Proposed |
