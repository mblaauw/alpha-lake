# ADR-0001: DuckLake as lakehouse format and catalog

**Status:** Proposed

**Context:**
Alpha-Lake needs a lakehouse format that supports ACID transactions, time travel, and SCD2 operations on Parquet data. DuckLake is a catalog built on DuckDB that provides these capabilities with a Delta-compatible storage layer.

**Decision:**
Use DuckLake as the lakehouse catalog and storage format. DuckLake provides:
- ACID transactions via Delta-compatible commits
- Time travel via snapshot isolation
- Native DuckDB SQL interface
- S3/MinIO compatible storage backend
- SCD2 operations via SQL MERGE with append-only semantics

**Consequences:**
- Positive: Native DuckDB integration, no separate metastore, simple deployment
- Positive: Time travel enabled out of the box for reproducibility
- Negative: Tied to DuckDB ecosystem; migration to Spark/Trino would require rewrite
- Negative: DuckLake 1.0 is relatively new; ecosystem maturity considerations

**References:**
- DESIGN.md §3.1

**Date:** 2026-06-18
