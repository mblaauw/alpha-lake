# ADR-0008: dlt for ingestion framework with idempotency

**Status:** Superseded

**Context:**
Alpha-Lake needs a robust ingestion framework that handles incremental loading, schema evolution, retries, and idempotency. Building this from scratch would be complex and error-prone.

**Decision (original, now superseded):**
Use dlt (data load tool) >= 1.0 for extract mechanics, incremental cursor state, retries, and raw/staging landing. dlt provides:
- Incremental loading with cursor-based state
- Schema evolution and contracts
- Built-in retry and error handling
- Extensible via custom sources and resources

dlt does not own canonical bitemporal SCD2. Alpha-Lake owns canonical normalization, Patito validation, `version_hash`, and the DuckDB SQL MERGE into DuckLake. Idempotency is achieved by combining dlt's incremental state with raw `content_hash` archive deduplication and canonical `version_hash` semantic deduplication.

**Superseded by:**
Connectors are hand-written `httpx` + `tenacity` functions behind a `get_connector()` registry dispatch. The registry provides per-source auth, rate-limit, and retry configuration from `source_registry` data — no dlt dependency, no incremental cursor abstraction. Per-entity outcome ledgers (`ok`, `empty`, `failed`, `quarantined`) replace dlt's incremental state for idempotency tracking. See `src/alpha_lake/connectors/__init__.py`, DESIGN.md §17, ADR-0023.

**Consequences (retrospective):**
- Positive: Zero external ingestion framework dependency
- Positive: Per-source auth, rate-limit, and retry live in registry data, not code
- Positive: Simpler debug and test path (no dlt state machinery)
- Negative: Must maintain per-source connector functions (one per dataset/supplier pair)
- Negative: No incremental cursor tracking — caller manages idempotency via outcome ledger

**References:**
- DESIGN.md §17
- ADR-0023

**Date:** 2026-06-18
**Superseded:** 2026-06-20
