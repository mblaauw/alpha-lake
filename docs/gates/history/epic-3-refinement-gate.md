# Refinement Gate: Epic 3 → Phase 4

**Status:** Assessment complete — epic closing
**Last assessed:** 2026-06-19
**Reviewers:** Dev, PO, Architect, UX, Systems Designer, Data Architect, Data Engineer

## Child Issue Audit

| # | Title | PR | Status |
|---|-------|----|--------|
| 31 | Security master PIT resolution | #231 | Merged |
| 32 | Corporate actions ingestion pipeline | #234 | Merged |
| 33 | PIT-adjusted OHLCV views | #235 | Merged |
| 34 | Adjusted-price leakage detection | #236 | Merged |
| 58 | Refinement Gate doc | — | This document |
| 67 | ADR-0005 Security master | — | Closed (pre-PR rule) |
| 68 | ADR-0006 Adjusted prices | — | Closed (pre-PR rule) |
| 105 | EODHD corp actions resource | #233 | Merged |
| 106 | Tiingo corp actions resource | #233 | Merged |
| 107 | OpenFIGI connector | #232 | Merged |
| 137 | Delistings, symbol reuse, survivorship tests | #236 | Merged |

## Gate Criteria

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| G1 | Security master resolves symbol → security_id PIT | ✅ | `test_symbol_reuse`, `test_resolve_pit`, `test_delisted_security_not_found` |
| G2 | Deterministic security_id from stable identifiers | ✅ | `test_mint_security_id_deterministic`, `test_mint_security_id_priority` |
| G3 | Delistings, symbol reuse, survivorship-bias tested | ✅ | `test_symbol_reuse_correct_security`, `test_delisted_security_not_found` |
| G4 | Corporate actions ingested and stored as canonical facts | ✅ | `test_write_corp_actions`, `test_splits_from_json`, `test_dividends_from_json` |
| G5 | Adjusted views return correct PIT-bounded adjustments | ✅ | `test_split_adjusted_reduces_price`, `test_multiple_splits_compound` |
| G6 | No price leakage in adjusted views | ✅ | `test_adjustment_respects_pit_boundary`, `test_split_after_as_of_not_applied` |
| G7 | OpenFIGI connector follows existing patterns | ✅ | `connectors/openfigi.py` |
| G8 | All CI checks pass | ✅ | 64 tests, lint-imports KEPT |
| G9 | Refinement gate completed before Phase 4 begins | ✅ | This document |

## Risks & Gaps

| Risk | Impact | Mitigation |
|------|--------|------------|
| Total return adjustment not implemented | Dividend-adjusted views not available | `price_mode='total_return'` is accepted but currently behaves like `split_adjusted`. Requires dividend reinvestment math. |
| No live API tests for OpenFIGI/EODHD/Tiingo corp actions | Connector code may fail on real API responses | Requires API keys in CI. Manual smoke testing recommended. |
| Split compounding uses windowed product LN/EXP | Floating point precision edge cases possible at extreme ratios | Tests pass with 3 decimal places; monitor for edge cases. |

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

- [ ] **Pass** — Proceed to Phase 4
- [ ] **Conditional Pass** — Proceed with conditions (listed below)
- [ ] **Fail** — Remediation required before Phase 4

### Conditions / Remediation
