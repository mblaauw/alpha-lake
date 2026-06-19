# ADR-0001: DuckLake as lakehouse format and catalog

**Status:** Accepted

**Context:**
Alpha-Lake needs a lakehouse format that supports ACID transactions, time travel, and SCD2-style versioned writes on Parquet data. DuckLake keeps lake metadata in a SQL catalog and stores data as open Parquet files.

**Decision:**
Use DuckLake as the lakehouse catalog and storage format. DuckLake provides:
- ACID transactions via the DuckLake catalog
- Time travel via snapshot isolation
- Native DuckDB SQL interface
- S3-compatible storage backend
- SCD2 operations via SQL MERGE with append-only semantics

**Consequences:**
- Positive: Native DuckDB integration, no separate metastore, simple deployment
- Positive: Time travel enabled out of the box for reproducibility
- Negative: Tied to DuckDB ecosystem; migration to Spark/Trino would require rewrite
- Negative: DuckLake 1.0 is relatively new; ecosystem maturity considerations

**References:**
- DESIGN.md §16

**Date:** 2026-06-18
