# ADR-0001: DuckLake as lakehouse format and catalog

**Status:** Accepted

**Context:**
Alpha-Lake needs a lakehouse format that supports ACID transactions, time travel, and SCD2-style versioned writes on Parquet data. DuckLake keeps lake metadata in a SQL catalog and stores data as open Parquet files.

**Decision:**
Use **DuckLake v1.0** (`ducklake` DuckDB extension) as the native lakehouse format. This replaces the earlier custom implementation that manually called `postgres_attach`, loaded httpfs/parquet extensions, and configured S3 settings. The official DuckLake extension handles catalog management, extension loading, S3 configuration, ACID transactions, snapshots, time travel, and partitioning natively.

Connection is now a single ATTACH statement:

```sql
INSTALL ducklake;
LOAD ducklake;
ATTACH 'ducklake:postgres:dbname=lake_catalog host=postgres'
    AS lake_catalog (DATA_PATH 's3://lake/');
USE lake_catalog;
```

For embedded mode:

```sql
ATTACH 'ducklake:sqlite:data/lake.catalog'
    AS lake_catalog (DATA_PATH 'data/lake/');
USE lake_catalog;
```

Key features provided by the extension:
- ACID transactions with snapshot isolation
- Time travel via `FOR SYSTEM_TIME AS OF`
- Native DuckDB SQL interface
- S3-compatible storage backend (MinIO, S3, GCS, Azure)
- SCD2 operations via `MERGE INTO` with append-only semantics
- Partitioning via `ALTER TABLE ... SET PARTITIONED BY`
- Concurrent read/write access across multiple DuckDB instances
- Automatic extension management (httpfs, parquet, postgres, sqlite)

**Consequences:**
- Positive: Native DuckDB integration, no separate metastore, simple deployment
- Positive: Time travel enabled out of the box for reproducibility
- Positive: ~300 lines of custom catalog/extension/S3 code eliminated
- Positive: ACID transactions and snapshot isolation at the lake level
- Negative: Tied to DuckDB ecosystem; migration to Spark/Trino would require rewrite
- Negative: DuckLake v1.0 is new (April 2026); ecosystem maturity considerations
- Negative: `MERGE INTO` requires DuckLake-attached tables (not plain DuckDB)

**References:**
- https://ducklake.select/docs/stable/
- DESIGN.md §16

**Date:** 2026-06-20 (updated from 2026-06-18)
