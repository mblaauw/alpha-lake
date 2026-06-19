# ADR-0012: Stack-first Compose; all deps vendored in-repo

**Status:** Proposed

**Context:** The project must run end-to-end with no external services, supporting air-gapped deployment and reproducible environments.

**Decision:** Docker Compose is the reference runtime. All dependencies are pinned and vendored in-repo: `uv.lock`, `vendor/images/` for containers, `vendor/wheelhouse/` for Python deps.

**Consequences:**
- Positive: Fully reproducible, air-gap capable
- Positive: No external service dependency at runtime
- Negative: Larger repo size from vendored artifacts
- Negative: Container image updates require explicit vendoring step

**References:**
- DESIGN.md §23, §3

**Date:** 2026-06-18
