# ADR-0003: SCD2 on knowledge time boundary for canonical datasets

**Status:** Accepted

**Context:**
Corrections to market data must not overwrite history. Historical PIT queries must return the state as it was knowable at that time.

**Decision:**
Use SCD2 (Slowly Changing Dimension Type 2) on the `available_at` (knowledge time) column. Every semantic correction creates a new version with a new `available_at`. The `effective_date` identifies the logical row, `available_at` versions it, and `version_hash` identifies semantic row identity. Queries use `available_at <= as_of` to get the correct version.

**Consequences:**
- Positive: Full historical fidelity — no data ever overwritten
- Positive: PIT queries are simple range scans on available_at
- Negative: Storage grows with each correction cycle
- Negative: Requires periodic compaction for performance

**References:**
- DESIGN.md §9, §11, §16

**Date:** 2026-06-18
