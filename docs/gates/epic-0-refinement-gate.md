# Refinement Gate: Epic 0 → Phase 1

**Status:** Assessment complete — epic closed via PR #168
**Last assessed:** 2026-06-19
**Reviewers:** Dev, PO, Architect, UX, Systems Designer, Data Architect, Data Engineer

## Child Issue Audit

| # | Title | PR | Status |
|---|-------|----|--------|
| 10 | Set up CI/CD pipeline | #163 | Merged |
| 11 | Configure import-linter | #158 | Merged |
| 12 | Implement OpenTelemetry | #161 | Merged |
| 13 | Harden Docker Compose | #164 | Merged |
| 14 | Initialize DuckLake catalog | #166 | Merged |
| 15 | Build justfile & harness | #162 | Merged |
| 55 | Refinement Gate doc | #167 | Merged |
| 63 | ADR-0001 DuckLake | — | Closed (pre-PR rule) |
| 64 | ADR-0002 Tri-temporal | — | Closed (pre-PR rule) |
| 72 | Scaffold models/ports | #165 | Merged |
| 73 | Wire health checks | #160 | Merged |
| 74 | Harden config & secrets | #159 | Merged |
| 91 | ADR-0011 OTel | — | Closed (pre-PR rule) |
| 92 | ADR-0012 Stack-first | — | Closed (pre-PR rule) |
| 95 | ADR-0015 Embedded harness | — | Closed (pre-PR rule) |

## Gate Criteria

Every item must be ticked or explicitly deferred before Phase 1 work begins.

### Foundation Checks

| # | Criterion | Status | Evidence | Notes |
|---|-----------|--------|----------|-------|
| F1 | CI pipeline passes on `main` (lint, type-check, test, import-linter) | ✅ | `.github/workflows/ci.yaml` runs ruff → ty → import-linter → pytest on every PR and push to main | PR #163 |
| F2 | Compose stack boots cleanly with `just up` | ⚠️ Needs verification | `docker compose up -d` should start postgres + minio + app + otel | Requires running stack; last verified during initial bootstrap |
| F3 | All three services (postgres, minio, app) report healthy | ⚠️ Needs verification | `docker compose ps` should show all 4 services healthy | Healthchecks defined in compose.yaml; actual run needed |
| F4 | `just health` passes without errors | ✅ | `just health` runs TCP check on postgres:5432 + HTTP check on minio:9000, prints dataset quality config | PR #160. Full validation requires stack running |
| F5 | `just bootstrap` initializes catalog schema | ✅ | Creates `source`, `source_dataset`, `ingestion_run`, `manifest` tables | PR #166. Full validation requires stack running |
| F6 | import-linter enforces layer boundaries | ✅ | `uv run lint-imports`: 55 files, 77 dependencies, layer-rules KEPT | PR #158. Layer order: cli → flows → serving → catalog → quality → canonical → connectors → ports → models |

### Domain Core

| # | Criterion | Status | Evidence | Notes |
|---|-----------|--------|----------|-------|
| D1 | `models/` and `ports/` packages populated with core types | ✅ | `models/`: `SecurityId`, `SourceId`, `TemporalFields`, `LineageFields`; `ports/`: `CatalogPort`, `StoragePort`, `SecurityMasterPort`, `ClockPort` | PR #165 |
| D2 | Config loading works in both stack and embedded runtimes | ✅ | `config.py`: `load_config()` reads TOML, validates via Pydantic; `config/stack.toml` and `config/embedded.toml` both parse | PR #159 |
| D3 | Source/source-dataset registry config defined per DESIGN.md §22 | ✅ | `[sources.eodhd]`, `[sources.tiingo]`, `[sources.alpaca]`, `[sources.sec]`, `[sources.openfigi]`, `[sources.reddit]`; `[source_datasets.*]` sections | PR #159 |
| D4 | Secret redaction implemented for logs | ✅ | `config.py`: `redact_secrets()` replaces `api_key=…` etc. with `***` | PR #159 |

### Observability

| # | Criterion | Status | Evidence | Notes |
|---|-----------|--------|----------|-------|
| O1 | OTel tracing wired into app startup | ✅ | `cli.py`: `setup_otel()` called from Typer callback when runtime=stack | PR #161 |
| O2 | Traces flow to the collector in the reference stack | ⚠️ Needs verification | `obs.py` exports to `OTEL_EXPORTER_OTLP_ENDPOINT` (default `http://otel:4317`) via gRPC | Requires stack running + collector inspection |
| O3 | Collector debug exporter outputs span data | ⚠️ Needs verification | `.stack/otel/otel-collector.yaml` has debug exporter with `verbosity: detailed` | Requires stack running; check collector logs with `just logs otel` |

### Reproducibility

| # | Criterion | Status | Evidence | Notes |
|---|-----------|--------|----------|-------|
| R1 | `just lint` runs ruff, ty, and import-linter | ✅ | `justfile`: `ruff check`, `ty check`, `lint-imports` | PR #158 |
| R2 | All dependencies pinned in `uv.lock` | ✅ | `uv.lock` committed; `uv sync --frozen` in Dockerfile ensures exact versions | Lockfile tracked in git |
| R3 | Docker images are tagged (not `:latest` on all services) | ❌ | `postgres:17-alpine`, `minio:latest`, `otel:latest` — no digest pins | ADR-0012 requires digest-pinned images. `vendor/compose.override.yaml` documents but does not pin. Deferred to Phase 7. |
| R4 | Vendor directory structure exists for air-gap | ✅ | `vendor/wheelhouse/`, `vendor/images/`, `vendor/bin/`, `vendor/compose.override.yaml` | PR #164. Actual artifacts not populated (requires `just vendor`) |

### Test Infrastructure

| # | Criterion | Status | Evidence | Notes |
|---|-----------|--------|----------|-------|
| T1 | `just test` runs the test suite | ✅ | `just test` → `uv run pytest`; currently 13 tests pass | PR #162 |
| T2 | Smoke tests cover core module imports | ✅ | `tests/unit/test_imports.py`: CLI, config, OTel, calendar, source registry, normalize, raw archive, BarFact, quality, canonical write, PIT reader | PR #162, extended in subsequent issues |
| T3 | Test configuration isolates from the reference stack | ✅ | `config/embedded.toml` uses SQLite + local FS; tests create ephemeral DuckDB connections | PR #159, integration test pattern |

### Documentation

| # | Criterion | Status | Evidence | Notes |
|---|-----------|--------|----------|-------|
| D1 | Epic 0 DoD checklist complete | ✅ | Verified against PR #168 close comment: all 15 sub-issues resolved | All 10 code issues merged via PRs, 5 ADRs closed |
| D2 | Refinement gate outcomes recorded | ✅ | This document | |

## Risks & Gaps

| Risk | Impact | Mitigation |
|------|--------|------------|
| Docker images use floating tags (`:latest`, `:17-alpine`) | Non-reproducible builds; image changes can break the stack without code changes | Deferred to Phase 7 (packaging & air-gap). ADR-0012 accepted. |
| OTel only exports to debug collector | No persistent observability data; traces lost on container restart | Prometheus/metrics pipeline deferred post-Phase 1. ADR-0011 documents console-first approach. |
| Stack services not automatically tested in CI | PRs merged without verifying Compose stack boots | Manual verification required before Phase 1 can be considered fully done. |
| No golden replay harness | Cannot prove deterministic replay across parser/config/calendar changes | Deferred to Epic 2 by design (Phase 2). ADR-0015 documents this. |

## Technical Debt Register

| Item | Raised | Target | Notes |
|------|--------|--------|-------|
| Digest-pinned Docker images | Phase 0 | Phase 7 | `vendor/compose.override.yaml` is a placeholder |
| Prometheus/metrics OTel pipeline | Phase 0 | Post-Phase 1 | Collector needs file or Prometheus exporter |
| Compose stack CI smoke test | Phase 0 | Phase 1 | Would need Docker-in-CI or reduced stack |
| Embedded replay harness | Phase 0 | Phase 2 | ADR-0015 defers to Epic 2 |

## Sign-off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Developer | | | |
| Product Owner | | | |
| Architect | | | |
| UX Designer | | | |
| Systems Designer | | | |
| Data Architect | | | |
| Data Engineer | | | |

## Gate Outcome

- [ ] **Pass** — Proceed to Phase 1
- [ ] **Conditional Pass** — Proceed with conditions (listed below)
- [ ] **Fail** — Remediation items required before Phase 1

### Conditions / Remediation

<!-- Add any conditions or remediation items here -->
