# ADR-0011: OpenTelemetry OTLP collector in stack, console in harness

**Status:** Superseded by ADR-0027

**Context:** Observability needs differ between production (persistent, queryable) and development/testing (fast feedback, no infrastructure).

**Decision:** Use OpenTelemetry with OTLP exporter to a collector in the reference stack. The reference collector exports metrics to a queryable backend (Prometheus locally; file exporter acceptable for offline harnesses) and may keep debug output for development. The embedded harness uses console exporter only.

**Consequences:**
- Positive: Production-grade observability with no extra code path
- Positive: Fast feedback in tests
- Negative: Collector backend configuration must be maintained alongside the stack

**References:**
- DESIGN.md §20

**Date:** 2026-06-18
