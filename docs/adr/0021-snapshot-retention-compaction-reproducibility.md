# ADR-0021: Snapshot retention, compaction, and pinned reproducibility

**Status:** Accepted

**Context:**
DuckLake provides snapshot isolation and time travel. Alpha-Lake also promises pinned reproducibility: consumers can pin an `ingestion_run_id`/snapshot and reproduce the exact historical view. Physical Parquet compaction is still necessary for performance, especially over S3/RustFS, but compaction and snapshot expiry can break pinned backtests if retention is not explicit.

**Decision:**
Define retention and compaction as part of the storage contract.

- Compaction may rewrite physical Parquet files but must preserve the logical snapshot-to-data mapping for all retained snapshots.
- Any snapshot pinned by `ingestion_run_id`, fixture bundle, or published dataset version remains resolvable until its documented retention horizon expires.
- Default retention: retained/pinned snapshots are kept for at least 2 years; unpinned operational snapshots are kept for at least 180 days.
- Canonical Parquet files target 128-512 MB after compaction.
- Canonical bars partition by `effective_date` year/month and sort by `(security_id, effective_date, available_at)` to support PIT pruning.
- Expiring a pinned snapshot is an explicit administrative action with audit record, not an incidental side effect of compaction.

**Consequences:**
- Positive: Backtests and fixture bundles remain reproducible after physical file optimization.
- Positive: File-size and sort policy gives DuckDB/RustFS predictable read performance.
- Negative: Retention increases storage cost.
- Negative: Administrative tooling must distinguish pinned vs unpinned snapshots.

**References:**
- DESIGN.md §16, §21
- Related issues: #98

**Date:** 2026-06-19
