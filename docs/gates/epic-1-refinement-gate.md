# Refinement Gate: Epic 1 → Phase 2

**Status:** Pending
**Reviewers:** Dev, PO, Architect, UX, Systems Designer, Data Architect, Data Engineer

## Gate Criteria

Every item must be ticked before Phase 2 work begins.

### Pipeline Completeness

- [ ] EODHD daily bars connector fetches and archives raw data
- [ ] Tiingo daily bars connector fetches and archives raw data
- [ ] Raw archive stores content-addressed Zstd blobs
- [ ] Polars normalize parses raw JSON to typed canonical DataFrame
- [ ] Patito BarFact validates all required fields and constraints
- [ ] SCD2 canonical write preserves all historical knowledge-time versions
- [ ] PIT reader returns correct `available_at`-bounded results with source precedence

### Data Quality

- [ ] Market sanity checks (OHLC consistency, non-negative volume, positive open)
- [ ] Quarantine marks violated rows with full lineage
- [ ] Reconciliation tolerance config is applied per dataset
- [ ] Idempotency: duplicate raw payloads and canonical rows are skipped

### Testing

- [ ] Restatement proof: pre/post restatement PIT reads return correct version
- [ ] Leakage: no read returns data with `available_at > as_of`
- [ ] Bitemporal visibility: different `as_of` values see different `available_at` versions
- [ ] All CI checks pass (lint, type-check, import-linter, tests)

### Infrastructure

- [ ] Compose stack boots and `just health` passes
- [ ] `just bootstrap` initializes catalog
- [ ] DuckDB extensions (httpfs, parquet, postgres) auto-install
- [ ] CI runs on every PR

### Documentation

- [ ] Epic 1 DoD checklist is complete
- [ ] All child issue ACs are met
- [ ] bars.v1 contract exists at `contracts/bars.v1.yaml`
- [ ] Refinement gate outcomes recorded in this document

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
