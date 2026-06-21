# ADR-0027: Structured JSON logging replaces OpenTelemetry as default observability

**Status:** Accepted

**Context:**
OpenTelemetry (ADR-0011) was configured at CLI startup and a collector was part of the default Compose stack, but no spans, meters, counters, or traces were emitted anywhere in `src/`. The only installed backend was a debug exporter in the collector that printed to stdout — no Prometheus, no queryable backend existed. The `grpcio` dependency pulled ~40–50 MB into the default app image with zero realized value.

**Decision:**
Default observability is structured JSON logging (`--log-json` flag with `{"event": "...", "data": {...}}` envelope) plus CLI health commands that report catalog and dataset status. OpenTelemetry becomes a dormant opt-in extra:

1. `src/alpha_lake/obs.py` is guarded by `ALPHA_LAKE_OTEL_ENABLED` env var — it is a no-op by default and is not called at startup.
2. OTel dependencies live only in the optional `[otel]` extra and are not installed in the default Docker image.
3. The OTel collector service is removed from `compose.yaml` and is not started by `just up`.
4. The collector config file (`.stack/otel/otel-collector.yaml`) is deleted.

**Consequences:**
- Positive: ~40–50 MB smaller default Docker image (no grpcio).
- Positive: Simpler Compose stack (one fewer service).
- Positive: No unused instrumentation code in the startup path.
- Positive: Structured JSON logs work immediately with any log aggregator (no OTLP pipeline needed).
- Negative: No distributed tracing available without explicit opt-in.
- Negative: Future metrics (request rate, latency, error count) will need a plain Prometheus `/metrics` endpoint on the REST transport rather than an existing OTel pipeline.

**References:**
- DESIGN.md §20 (updated)
- ADR-0011 (superseded)
- ADR-0024 (serving architecture — future Prometheus `/metrics` endpoint)

**Date:** 2026-06-21
