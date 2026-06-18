# ADR-0008: dlt for ingestion framework with idempotency

**Status:** Proposed

**Context:**
Alpha-Lake needs a robust ingestion framework that handles incremental loading, schema evolution, retries, and idempotency. Building this from scratch would be complex and error-prone.

**Decision:**
Use dlt (data load tool) >= 1.0 as the ingestion framework. dlt provides:
- Incremental loading with cursor-based state
- SCD2 merge support
- Schema evolution and contracts
- Built-in retry and error handling
- Extensible via custom sources and resources

Idempotency is achieved by combining dlt's incremental state with content-addressed raw archive deduplication.

**Consequences:**
- Positive: Battle-tested ingestion patterns, reduced code to maintain
- Positive: Schema evolution handled automatically
- Negative: Additional dependency and abstraction layer
- Negative: dlt's SCD2 may need customization for Alpha-Lake's bitemporal model

**References:**
- DESIGN.md §4

**Date:** 2026-06-18
