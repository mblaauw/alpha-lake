# Refinement Gate: Epic #374 → (next epic)

**Status:** Assessment complete — epic closing
**Last assessed:** 2026-06-22

## Child Issue Audit

| # | Title | PR | Status |
|---|-------|----|--------|
| 375 | Phase 0.1 — Per-source quota budgets | ccc3bd6 | Merged |
| 376 | Phase 0.2 — Keyless / degraded fallback per source | ccc3bd6 | Merged |
| 377 | Phase 0.3 — Chunked-window fetch helper | ccc3bd6 | Merged |
| 378 | Phase 0.4 — SEC User-Agent contact compliance | ccc3bd6 | Merged |
| 379 | Phase 0.5 — Generalize kernel precedence for all multi-source datasets | ccc3bd6 | Merged |
| 380 | Phase 1.1 — `macro_series`: FRED macroeconomic series with full revision history | 3341960 | Merged |
| 381 | Phase 1.2 — `economic_calendar`: Known-future macro events | 9254208 | Merged |
| 382 | Phase 1.3 — `analyst_estimates`: Recommendation trends & rating changes | 5b71feb | Merged |
| 383 | Phase 1.4 — `congress_trades`: Legislative trade disclosures | 7110a1e | Merged |
| 384 | Phase 1.5 — Activate `news_articles` with concrete sources (Finnhub + Marketaux) | ba1a4cb | Merged |
| 385 | Phase 1.6 — Activate `sentiment_annotations` with labeled sources | cb7ef16 | Merged |
| 386 | Phase 1.7 — Activate `attention_metrics`: Aggregated social attention (ApeWisdom) | cb7ef16 | Merged |
| — | *Phase 1.8 — insider_tx enrichment (Finnhub + CIK resolution)* | cd11da3 | Merged |
| 388 | Phase 2.0 — Wire `technical_indicators` DATASETS entry | 2a36fea | Merged |
| 389 | Phase 2.1 — Extend `technical_indicators`: returns panel, distance-to-MA, ATR%, realized vol, RVOL, dollar volume, 52-week, gap % | 2a36fea | Merged |
| 390 | Phase 2.2 — `relative_strength` (new convenience dataset) | a9a1d5f | Merged |
| 391 | Phase 2.3 — `market_breadth` (new convenience dataset) | ad1d579 | Merged |
| 392 | Phase 2.4 — `vol_term_structure` (new dataset) + contango spread | c140df4 | Merged |
| 393 | Phase 2.5 — Macro transforms: YoY/MoM derived from `macro_series` vintages | cd693e6 | Merged |
| 394 | Phase 2.6 — Event aggregations: insider clusters, attention deltas, sentiment ratios | 911f957 | Merged |
| 395 | Phase 3.1 — Reconciliation blocks for multi-source datasets | 13f5ba6 | Merged |
| 396 | Phase 3.2 — Dagster assets for new ingestion + derived pipelines | 13f5ba6 | Merged |
| 397 | Phase 3.3 — Source-health doc (registry-as-data) | 13f5ba6 | Merged |
| 398 | Phase 3.4 — Promotion gates: experimental -> supported | 13f5ba6 | Merged |

## Metrics

- **237 tests passing** (up from ~100 at start of the epic)
- **import-linter**: KEPT
- **ty**: All checks passed
- **ruff**: All checks passed
- **Forbidden-token grep**: Clean (no strategy semantics in `derived/`)
- **234 test files** across unit, boundary, contract, and replay suites

## Sign-off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Developer | | | |

## Outcome

- [x] **Pass** — Proceed to next epic
