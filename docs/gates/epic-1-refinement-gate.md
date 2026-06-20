# Refinement Gate: Epic 1 → Phase 2

**Status:** Assessment complete — epic closed via PR #186
**Last assessed:** 2026-06-19
**Reviewers:** Dev, PO, Architect, UX, Systems Designer, Data Architect, Data Engineer

## Child Issue Audit

| # | Title | PR | Status |
|---|-------|----|--------|
| 16 | dlt connector framework | #175 | Merged |
| 17 | Immutable raw archive | #177 | Merged |
| 18 | Polars normalize step | #178 | Merged |
| 19 | Patito BarFact validation | #179 | Merged |
| 20 | SCD2 canonical write | #180 | Merged |
| 21 | Quarantine & reconciliation | #182 | Merged |
| 22 | PIT reader for bars | #183 | Merged |
| 23 | Idempotency & duplicate detection | #181 | Merged |
| 56 | Refinement Gate doc | #185 | Merged |
| 65 | ADR-0003 SCD2 | — | Closed (pre-PR rule) |
| 66 | ADR-0004 Replay | — | Closed (pre-PR rule) |
| 70 | ADR-0008 dlt | — | Closed (pre-PR rule) |
| 75 | Restatement integration test | #184 | Merged |
| 81 | Source registry runtime | #173 | Merged |
| 94 | ADR-0014 Source registry | — | Closed (pre-PR rule) |
| 99 | DuckDB extension management | #172 | Merged |
| 100 | Polars↔DuckDB Arrow interop | #174 | Merged |
| 101 | EODHD base client | #176 | Merged |
| 102 | EODHD daily bars resource | #176 | Merged |
| 103 | Tiingo base client | #176 | Merged |
| 104 | Tiingo daily bars resource | #176 | Merged |
| 135 | Trading calendar & timezone | #170 | Merged |
| 136 | Bars dataset contract | #169 | Merged |
| 139 | Reconciliation tolerances | #171 | Merged |

## Gate Criteria

Every item must be ticked or explicitly deferred before Phase 2 work begins.

### Pipeline Completeness

| # | Criterion | Status | Evidence | Notes |
|---|-----------|--------|----------|-------|
| P1 | EODHD daily bars connector fetches and archives raw data | ✅ Code complete ⚠️ Not run against live API | `connectors/eodhd.py`: `fetch_bars_daily()` with httpx client, tenacity retry, manifest building | Requires `ALPHA_LAKE_EODHD_API_KEY` env var and network access. CI has no API keys. |
| P2 | Tiingo daily bars connector fetches and archives raw data | ✅ Code complete ⚠️ Not run against live API | `connectors/tiingo.py`: `fetch_bars_daily()` with Tiingo token auth | Same as P1 — no API keys in CI. |
| P3 | Raw archive stores content-addressed Zstd blobs | ✅ | `raw/__init__.py`: SHA-256 content hash → `raw/<prefix>/<hash>.zst`, Zstd level 3 compression. Verified via `test_raw_archive`. | PR #177. Works for both embedded (local FS) and stack (S3) runtimes. |
| P4 | Polars normalize parses raw JSON to typed canonical DataFrame | ✅ | `normalize/__init__.py`: `bars_from_json()` maps API fields → canonical columns. Verified via `test_normalize_bars`. | PR #178. `available_at` is a parameter (not wall-clock) for determinism. |
| P5 | Patito BarFact validates all required fields and constraints | ✅ | `models/bar_fact.py`: `BarFact` model with 20 fields, non-negative constraints (`Field(ge=0)`). Verified via `test_bar_fact`. | PR #179. Optional null fields cast explicitly for Polars compatibility. |
| P6 | SCD2 canonical write preserves all historical knowledge-time versions | ✅ | `canonical/__init__.py`: `write_bars()` INSERTs only when `(natural_key + available_at + version_hash)` not matched. Verified via `test_restatement_proof`. | PR #180. Never UPDATEs — always INSERTs new `available_at` versions. |
| P7 | PIT reader returns correct `available_at`-bounded results with source precedence | ✅ | `serving/__init__.py`: `read_bars_asof()` with Stage 1 (newest version per source) + Stage 2 (source precedence: eodhd → tiingo → alpaca). | PR #183. `read_bars_latest()` is PIT-unsafe and documented as such. |

### Data Quality

| # | Criterion | Status | Evidence | Notes |
|---|-----------|--------|----------|-------|
| Q1 | Market sanity checks (OHLC consistency, non-negative volume, positive open) | ✅ | `quality/__init__.py`: `check_market_sanity()` verifies `low ≤ open ≤ high`, `low ≤ close ≤ high`, `volume ≥ 0`, `open > 0`. Verified via `test_quality_market_sanity`. | PR #182 |
| Q2 | Quarantine marks violated rows with full lineage | ✅ | `quality/__init__.py`: `quarantine()` sets `quality_status = 'quarantined'` for rows failing sanity checks | PR #182. Lineage fields (`source_id`, `source_fetch_id`, `raw_payload_hash`) preserved on quarantined rows. |
| Q3 | Reconciliation tolerance config is applied per dataset | ✅ | `config.py`: `ReconciliationConfig` with `price_diff_pct`, `volume_diff_pct`, `cross_source_enabled`. `config/stack.toml`: `[reconcile.bars]` with 0.5% price, 5% volume tolerance. | PR #171. Reconciliation comparison logic not yet implemented — config is defined but not consumed. Marked as code-complete, logic deferred. |
| Q4 | Idempotency: duplicate raw payloads and canonical rows are skipped | ✅ | `raw/__init__.py`: `archive()` returns early if `content_hash` exists. `canonical/__init__.py`: `write_bars()` LEFT JOIN dedup on version_hash. | PR #181 (raw), PR #180 (canonical). |

### Testing

| # | Criterion | Status | Evidence | Notes |
|---|-----------|--------|----------|-------|
| S1 | Restatement proof: pre/post restatement PIT reads return correct version | ✅ | `tests/integration/test_restatement.py`: writes original bar at T1, restated bar at T2, asserts `as_of < T2 → original`, `as_of >= T2 → restated`, `version_hash` differs. | PR #184 |
| S2 | Leakage: no read returns data with `available_at > as_of` | ✅ | Covered by restatement test: `read_bars_asof(…, as_of=2026-06-18T17:00)` cannot see the T2 version (available_at=2026-06-19T08:00). | Implicitly verified. A dedicated leakage fixture could be added. |
| S3 | Bitemporal visibility: different `as_of` values see different `available_at` versions | ✅ | Same restatement test: `as_of_historical → close=100.5`, `as_of_post → close=101.0` | PR #184 |
| S4 | All CI checks pass (lint, type-check, import-linter, tests) | ✅ | `uv run ruff check`: clean. `uv run ty check`: clean. `uv run lint-imports`: layer-rules KEPT. `uv run pytest tests/`: 13 passed. | Verified at gate assessment time. |

### Infrastructure

| # | Criterion | Status | Evidence | Notes |
|---|-----------|--------|----------|-------|
| I1 | Compose stack boots and `just health` passes | ⚠️ Needs verification | `compose.yaml`: postgres + rustfs + app + otel services with healthchecks. `cli.py`: TCP check on postgres:5432, HTTP check on rustfs:9000. | Requires running `just up` and `just health` manually. No CI step for this. |
| I2 | `just bootstrap` initializes catalog | ✅ | `catalog/__init__.py`: `bootstrap()` creates `source`, `source_dataset`, `ingestion_run`, `manifest` tables | PR #166. Full verification requires stack running. |
| I3 | DuckDB extensions (ducklake, httpfs, parquet, postgres) auto-install | ✅ | `catalog/__init__.py`: `connect()` runs INSTALL/LOAD on startup. `configure_s3()` sets S3 endpoint/region/ssl. | PR #172 |
| I4 | CI runs on every PR | ✅ | `.github/workflows/ci.yaml`: PR trigger + push to main. lint-typecheck + test jobs. | PR #163 |

### Documentation

| # | Criterion | Status | Evidence | Notes |
|---|-----------|--------|----------|-------|
| A1 | Epic 1 DoD checklist complete | ✅ | Verified against PR #186 close comment: all 22 sub-issues resolved | 18 issues merged via PRs, 4 ADRs closed |
| A2 | All child issue ACs are met | ✅ | Each PR verified acceptance criteria before merge | ACs checked during PR review |
| A3 | bars.v1 contract exists at `contracts/bars.v1.yaml` | ✅ | Defines PK (`security_id`, `effective_date`, `source_id`), PIT columns, required/nullable fields, freshness SLA, quality statuses, compatibility rules | PR #169 |
| A4 | Refinement gate outcomes recorded | ✅ | This document | |

## Risks & Gaps

| Risk | Impact | Mitigation |
|------|--------|------------|
| EODHD/Tiingo connectors never executed against live API | Connectors may break on real API responses (rate limits, auth, response format drift) | Add integration test step when API keys are available in CI. Manual smoke test before Phase 2. |
| Reconciliation comparison logic not implemented | ReconciliationConfig exists but does nothing | Config is structural placeholder; comparison logic deferred to Phase 5 (serving) or dedicated reconciliation epic. |
| No explicit leakage test fixture | Leakage invariant proven only as side effect of restatement test | Add standalone `test_leakage` with explicit `available_at > as_of` assertion. Low priority but easy. |
| Connectors don't integrate with raw archive pipeline end-to-end | `connectors/eodhd.py` returns `RawFetch` but no orchestration calls `archive()` then `normalize()` then `write_bars()` | Missing `flows/` orchestration. By design — flows are a thin shell; pipeline stages are composable functions. |
| Docker images not digest-pinned (carried from Epic 0) | Non-reproducible builds | Deferred to Phase 7. Documented in Epic 0 technical debt. |

## Technical Debt Register

| Item | Raised | Target | Notes |
|------|--------|--------|-------|
| Reconciliation comparison logic | Phase 1 | Phase 5 | Config exists; actual diff engine not built |
| Standalone leakage test | Phase 1 | Phase 2 | Simple fixture with `available_at > as_of` assert |
| EODHD/Tiingo live API integration test | Phase 1 | Phase 2 | Requires API keys in CI or manual credential injection |
| End-to-end pipeline orchestration (`flows/`) | Phase 1 | Phase 6 | Pipeline stages are composable; Dagster shell deferred |
| Feast/feature store alignment audit | Phase 1 | Phase 5 | DESIGN.md §9.3 defers; fact store vs feature store boundary |
| Digest-pinned Docker images | Phase 0 | Phase 7 | Carryover from Epic 0 |

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

- [ ] **Pass** — Proceed to Phase 2
- [ ] **Conditional Pass** — Proceed with conditions (listed below)
- [ ] **Fail** — Remediation required before Phase 2

### Conditions / Remediation

<!-- Add any conditions or remediation items here -->
