# ADR-0015: Embedded mode demoted to test/debug/golden-replay harness

**Status:** Proposed

**Context:** Early designs considered embedded mode as a first-class runtime. This creates two code paths that must both work, multiplying maintenance burden.

**Decision:** The Compose stack is the only first-class runtime. The embedded (SQLite+localFS) mode exists solely for tests, debugging, fixture generation, and golden replay — never as a product path.

**Consequences:**
- Positive: Single production runtime to maintain
- Positive: Stack boundary exercised from day one
- Negative: All development happens in Compose
- Negative: Slightly slower inner dev loop

**References:**
- DESIGN.md §3, §27 Phase 0, §27 Phase 1b

**Date:** 2026-06-18
