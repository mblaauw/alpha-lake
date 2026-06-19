# Refinement Gate: Epic 2 → Phase 3

**Status:** Assessment complete — epic closing
**Last assessed:** 2026-06-19
**Reviewers:** Dev, PO, Architect, UX, Systems Designer, Data Architect, Data Engineer

## Child Issue Audit

| # | Title | PR | Status |
|---|-------|----|--------|
| 24 | SQLite/local-fs embedded harness | #189 | Merged |
| 25 | Golden replay engine | #190 | Merged |
| 26 | Pytest fixtures for replay & contract | #192 | Merged |
| 27 | Fixture-hash stability | #193 | Merged |
| 28 | Connector-contract tests | #194 | Merged |
| 29 | Bitemporal-visibility tests | #195 | Merged |
| 30 | Adjusted-price leakage tests | #196 | Merged |
| 57 | Refinement Gate doc | — | This document |
| 69 | ADR-0007 Embedded harness | — | Closed (pre-PR rule) |
| 76 | Harness equivalence | #197 | Merged |
| 77 | Freeze-fixtures CLI command | #191 | Merged |

## Gate Criteria

Every item must be ticked or explicitly deferred before Phase 3 work begins.

### Harness & Replay

| # | Criterion | Status | Evidence | Notes |
|---|-----------|--------|----------|-------|
| H1 | Embedded harness uses SQLite DuckLake + local filesystem | ✅ | `harness.py`: `EmbeddedHarness` with in-memory DuckDB + temp directory. `conftest.py`: session-scoped fixture. | PR #189 |
| H2 | Golden replay engine works for bars flow | ✅ | `replay/__init__.py`: `freeze_output()`, `check_replay()`, `load_golden_hash()`. Verified via `test_golden_replay.py` (2 tests). | PR #190. `just replay` collects 2 tests. |
| H3 | Fixture hashes stable across runs | ✅ | `test_hash_deterministic`: same inputs → identical hash. `test_hash_changes_on_restatement`: restated data → different hash. | PR #193 |
| H4 | Replay validates business output AND bitemporal row visibility | ✅ | `test_hash_covers_visibility`: visibility set hash (PK + available_at + version_hash + source_id) differs across as_of. | PR #193 |

### Test Coverage

| # | Criterion | Status | Evidence | Notes |
|---|-----------|--------|----------|-------|
| T1 | Connector-contract tests with recorded fixtures | ✅ | `test_connector_contract.py`: 5 tests covering normalize→BarFact, manifest, raw archive, canonical write. | PR #194 |
| T2 | Bitemporal-visibility tests | ✅ | `test_bitemporal_visibility.py`: 5 tests covering available_at ≤ as_of, newest version, independent securities. | PR #195 |
| T3 | Adjusted-price leakage tests | ✅ | `test_adjusted_price_leakage.py`: 3 tests with synthetic adjustment data verifying PIT boundary. | PR #196. Full corp actions implementation deferred to Epic 3. |
| T4 | Stack-vs-embedded equivalence proven | ✅ | `test_harness_equivalence.py`: deterministic output matches frozen golden hash. Architectural: same code paths, only I/O differs. | PR #197 |
| T5 | `freeze-fixtures` CLI produces frozen fixtures | ✅ | `fixtures/__init__.py`: runs pipeline on harness, saves Parquet + hash. Both `just freeze-fixtures` and `alpha-lake freeze-fixtures` work. | PR #191 |

### Testing Metrics

| # | Criterion | Status | Evidence | Notes |
|---|-----------|--------|----------|-------|
| M1 | All test categories have at least one passing test | ✅ | 34 tests across unit, integration, replay, contract, boundary directories | |
| M2 | All CI checks pass | ✅ | `uv run pytest tests/`: 34 passed. `uv run lint-imports`: KEPT. `uv run ruff check`: clean. | |
| M3 | `just replay` exits 0 | ✅ | Collects and passes 2 replay tests | |

### Documentation

| # | Criterion | Status | Evidence | Notes |
|---|-----------|--------|----------|-------|
| D1 | Epic 2 DoD checklist complete | ✅ | Verified: all 7 DoD items satisfied | |
| D2 | All child issue ACs are met | ✅ | Each PR verified acceptance criteria before merge | |
| D3 | Refinement gate outcomes recorded | ✅ | This document | |

## Risks & Gaps

| Risk | Impact | Mitigation |
|------|--------|------------|
| Stack-vs-embedded equivalence proven architecturally, not empirically | SQLite vs Postgres dialect differences may cause undetected divergence | Documented in ADR-0007. Mitigated by using DuckDB SQL (same dialect) as the common execution layer for both modes. |
| Adjusted-price tests use synthetic data, not real corp actions | Tests verify PIT boundary but not adjustment computation correctness | Epic 3 implements real corp actions; tests will be extended then. |
| No replay test for connector integration at live API level | Connector parsing may fail on real API response format drift | Requires API keys in CI; deferred. |

## Technical Debt Register

| Item | Raised | Target | Notes |
|------|--------|--------|-------|
| Live API integration test for connectors | Phase 2 | Phase 3 | Requires `ALPHA_LAKE_EODHD_API_KEY` in CI |
| Adjusted-price test with real corp actions | Phase 2 | Phase 3 | Synthetic data used as proxy; Epic 3 will provide real data |
| Golden replay test that runs `just freeze-fixtures` + `just replay` as a single assertion | Phase 2 | Phase 3 | Would prove end-to-end freeze→replay determinism in one step |

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

- [ ] **Pass** — Proceed to Phase 3
- [ ] **Conditional Pass** — Proceed with conditions (listed below)
- [ ] **Fail** — Remediation required before Phase 3

### Conditions / Remediation
