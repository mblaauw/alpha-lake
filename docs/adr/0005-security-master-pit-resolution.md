# ADR-0005: Security master PIT resolution (symbol → security_id)

**Status:** Accepted

**Context:**
Symbols (tickers) change over time due to mergers, rebranding, and delisting. Backtests and research need a stable identifier that tracks the same security across symbol changes.

**Decision:**
Maintain a security master that assigns a persistent deterministic `security_id` to each distinct security. `security_id` is minted from stable identifiers, never from a symbol and never from randomness. The minting input is the first available stable-key tuple in priority order: FIGI, then CIK, then ISIN, then a documented composite fallback (`exchange + source_native_id + first_listed_date`) only when no global identifier is available.

The master records symbol → security_id mappings with date ranges. Resolution is PIT-aware: a given `as_of` returns the correct `security_id` for that point in time. The security master itself is an SCD2 dataset. If FIGI/CIK/ISIN disagree across sources, the row is quarantined for identity conflict unless an explicit mapping already exists.

**Consequences:**
- Positive: Stable joins across datasets and time
- Positive: Symbol changes do not break historical queries
- Positive: Golden replay reproduces identical `security_id` values
- Negative: Additional resolution step at query time
- Negative: Security master must be maintained and curated

**References:**
- DESIGN.md §10, §25

**Date:** 2026-06-18
