# ADR-0006: Read-time adjusted price computation (never materialized)

**Status:** Accepted

**Context:**
Adjusted prices depend on corporate actions (splits, dividends) that were knowable at the time of the PIT query. Storing pre-computed adjusted prices would require recomputation on every corp action change.

**Decision:**
Compute adjusted prices at read time only. Raw OHLCV bars are stored unadjusted. Corporate actions are stored as separate canonical tables. The PIT reader computes adjustment factors from corp actions knowable at `as_of` and applies them to raw prices on-the-fly. Adjusted prices are never materialized.

**Consequences:**
- Positive: No stale adjusted views — always reflects current corp action knowledge
- Positive: Single source of truth (raw bars)
- Negative: Read-time computation cost for adjusted views
- Negative: More complex PIT reader implementation

**References:**
- DESIGN.md §12

**Date:** 2026-06-18
