# ADR-0011: OpenTelemetry OTLP collector in stack, console in harness

**Status:** Proposed

**Context:** Observability needs differ between production (persistent, queryable) and development/testing (fast feedback, no infrastructure).

**Decision:** Use OpenTelemetry with OTLP exporter to a collector in the reference stack. The embedded harness uses console exporter only.

**Consequences:**
- Positive: Production-grade observability with no extra code path
- Positive: Fast feedback in tests
- Negative: Two receiver configurations to maintain

**References:**
- DESIGN.md §19

**Date:** 2026-06-18
