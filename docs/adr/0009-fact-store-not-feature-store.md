# ADR-0009: Fact store + transform library, never a feature store

**Status:** Proposed

**Context:** The lake must not materialize strategy-windowed features (EMA 50, ATR 14) — windows are strategy choices. Consumers should compute their own features from clean PIT data using a provided transform library.

**Decision:** The lake stores only raw facts. A neutral transform library (pure Python/DuckDB functions) is provided for consumers to compose. No strategy-semantic functions (scores, ranks, signals) are shipped.

**Consequences:**
- Positive: Single source of truth for facts
- Positive: No coupling between lake versioning and strategy feature definitions
- Negative: Consumers must compute their own feature windows

**References:**
- DESIGN.md §14
- Derived transforms issue: #82

**Date:** 2026-06-18
