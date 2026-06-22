# Operations Guide

## DuckDB Memory Sizing

### Setting Memory Limits

Configure DuckDB memory via `SET memory_limit = '...'` in the connection or
the `ALPHA_LAKE_DUCKDB_MEMORY` environment variable:

```sql
SET memory_limit = '2GB';
SET temp_directory = '/tmp/duckdb_spill';
```

### Spill-to-Disk

When memory is insufficient, DuckDB spills to `temp_directory`. Ensure the
temp directory has enough free space (at least 2× the dataset working set).

### Per-Dataset Working Set Estimates

| Dataset | Estimated size/year | Ingest memory | Compact memory | Replay memory |
|---------|--------------------|---------------|----------------|---------------|
| lake_bars | ~50 MB | 256 MB | 512 MB | 1 GB |
| fundamentals | ~20 MB | 256 MB | 512 MB | 512 MB |
| corp_actions | ~5 MB | 128 MB | 256 MB | 256 MB |

### Ports

| Service | Port |
|---------|------|
| Postgres | 5432 |
| RustFS S3 | 9000 |
| RustFS console | 9001 |
| FastAPI (REST API + Lake Watch dashboard) | 8000 |

### Container Sizing

| Operation | Minimum memory | Recommended |
|-----------|--------------|-------------|
| Ingest | 512 MB | 1 GB |
| Compact | 1 GB | 2 GB |
| Replay | 1 GB | 4 GB |
| Serving | 256 MB | 512 MB |

### Starting the server

```bash
# Via Docker Compose (starts automatically with just up):
docker compose up -d

# Manually (one-off, with port forwarding):
docker compose run --rm --service-ports app serve

# Just the server (without compose stack):
just serve
```

The FastAPI server serves the REST API at `/v1/*` and the Lake Watch dashboard
at `http://localhost:8000/`. The dashboard is enabled via `ALPHA_LAKE_DASHBOARD_ENABLED=true`
(set in `compose.yaml`).

### Pushdown vs Pull

- **Pushdown** (filter/limit at DuckDB level) is preferred — it reduces data
  transferred from the catalog.
- **Pull** (full table scan) should only be used when pushdown filters cannot
  express the query.
- Use `EXPLAIN ANALYZE` to identify full scans vs pushdown.

## Catalog Growth Monitoring

### Expected Growth Patterns

- DuckLake snapshots accumulate on every committed write.
- Each snapshot stores metadata + inlined small rows.
- Expect ~100 KB per snapshot for typical ingest operations.
- The `ducklake_expire_snapshots` function can prune old snapshots.

### Monitoring Thresholds

| Metric | Warning | Critical |
|--------|---------|----------|
| Snapshot count | >1000 | >5000 |
| Catalog metadata size | >1 GB | >5 GB |
| Per-table rows | >10M | >50M |
