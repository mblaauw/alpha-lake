# ADR-0008: dlt for ingestion framework with idempotency

**Status:** Accepted

**Context:**
Alpha-Lake needs a robust ingestion framework that handles incremental loading, schema evolution, retries, and idempotency. Building this from scratch would be complex and error-prone.

**Decision:**
Use dlt (data load tool) >= 1.0 for extract mechanics, incremental cursor state, retries, and raw/staging landing. dlt provides:
- Incremental loading with cursor-based state
- Schema evolution and contracts
- Built-in retry and error handling
- Extensible via custom sources and resources

dlt does not own canonical bitemporal SCD2. Alpha-Lake owns canonical normalization, Patito validation, `version_hash`, and the DuckDB SQL MERGE into DuckLake. Idempotency is achieved by combining dlt's incremental state with raw `content_hash` archive deduplication and canonical `version_hash` semantic deduplication.

**Consequences:**
- Positive: Battle-tested ingestion patterns, reduced code to maintain
- Positive: Schema evolution handled automatically
- Negative: Additional dependency and abstraction layer
- Negative: Alpha-Lake must maintain the canonical bitemporal write path itself

**References:**
- DESIGN.md §17

**Date:** 2026-06-18
