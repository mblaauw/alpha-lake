# Refinement Gate: Epic 0 → Phase 1

**Status:** Pending
**Reviewers:** Dev, PO, Architect, UX, Systems Designer, Data Architect, Data Engineer

## Gate Criteria

Every item must be ticked before Phase 1 work begins.

### Foundation Checks

- [ ] CI pipeline passes on `main` (lint, type-check, test, import-linter)
- [ ] Compose stack boots cleanly with `just up`
- [ ] All three services (postgres, rustfs, app) report healthy
- [ ] `just health` passes without errors
- [ ] `just bootstrap` initializes the catalog schema
- [ ] import-linter enforces layer boundaries

### Domain Core

- [ ] `models/` and `ports/` packages are populated with core types
- [ ] Config loading works in both stack and embedded runtimes
- [ ] Source/source-dataset registry config is defined per DESIGN.md §22
- [ ] Secret redaction is implemented for logs

### Observability

- [ ] OTel tracing is wired into app startup
- [ ] Traces flow to the collector in the reference stack
- [ ] Collector debug exporter outputs span data

### Reproducibility

- [ ] `just lint` runs ruff, ty, and import-linter
- [ ] All dependencies are pinned in `uv.lock`
- [ ] Docker images are tagged (not `:latest` on all services)
- [ ] Vendor directory structure exists for air-gap

### Test Infrastructure

- [ ] `just test` runs the test suite
- [ ] Smoke tests cover core module imports
- [ ] Test configuration isolates from the reference stack

### Documentation

- [ ] Epic 0 DoD checklist is complete
- [ ] Refinement gate outcomes are recorded in this document

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
