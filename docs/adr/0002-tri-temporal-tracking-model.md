# ADR-0002: Tri-temporal tracking model (valid, knowledge, system time)

**Status:** Proposed

**Context:**
Market data has three distinct time dimensions: when a fact is true in the market (valid time), when the lake could first serve it (knowledge time / available_at), and when the database committed it (system time for audit).

**Decision:**
Track all three temporal dimensions:
- `effective_date`: Valid time — when the fact is true in the market
- `available_at`: Knowledge time — when the lake first could serve this fact (PIT boundary)
- System time: DuckLake snapshot/commit timestamp for audit trail

PIT queries always filter on `available_at <= as_of`. Valid time is used for effective joins.

**Consequences:**
- Positive: Point-in-time correctness for backtesting and research
- Positive: Full audit trail of what was knowable and when
- Negative: More complex queries (must always filter on available_at)
- Negative: Storage overhead from multiple versions on SCD2

**References:**
- DESIGN.md §3

**Date:** 2026-06-18
