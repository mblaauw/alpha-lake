# ADR-0005: Security master PIT resolution (symbol → security_id)

**Status:** Proposed

**Context:**
Symbols (tickers) change over time due to mergers, rebranding, and delisting. Backtests and research need a stable identifier that tracks the same security across symbol changes.

**Decision:**
Maintain a security master that assigns a persistent UUID-like `security_id` to each distinct security. The master records symbol → security_id mappings with date ranges. Resolution is PIT-aware: a given `as_of` returns the correct `security_id` for that point in time. The security master itself is an SCD2 dataset.

**Consequences:**
- Positive: Stable joins across datasets and time
- Positive: Symbol changes do not break historical queries
- Negative: Additional resolution step at query time
- Negative: Security master must be maintained and curated

**References:**
- DESIGN.md §4.1

**Date:** 2026-06-18
