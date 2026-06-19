# ADR-0009: Fact store + transform library, never a feature store

**Status:** Refined by ADR-0017

**Context:** The lake must not materialize strategy-windowed features (EMA 50, ATR 14) — windows are strategy choices. Consumers should compute their own features from clean PIT data using a provided transform library.

**Decision:** The lake stores only raw facts. A neutral transform library (pure Python/DuckDB functions) is provided for consumers to compose. No strategy-semantic functions (scores, ranks, signals) are shipped.

**Consequences:**
- Positive: Single source of truth for facts
- Positive: No coupling between lake versioning and strategy feature definitions
- Negative: Consumers must compute their own feature windows

**Notes:**
- ADR-0017 extends this decision by defining a comprehensive indicator library with an optional rebuildable cache. The core principle (lake stores canonical facts, not strategy features) is preserved.
- The phrase "lake stores only raw facts" is refined: the lake may cache derived indicators, but the cache is never canonical truth.

**References:**
- DESIGN.md §14
- ADR-0017: Derived technical indicator library
- Derived transforms issue: #82

**Date:** 2026-06-18
