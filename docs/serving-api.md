# Serving API — Python Reader Contracts

## Bars

| Function | Description | PIT-safe |
|----------|-------------|----------|
| `read_bars_asof(con, security_ids, as_of, ..., snapshot_id)` | Returns newest bars with `available_at <= as_of`. Optional `snapshot_id` pins DuckLake snapshot for reproducibility. | ✅ |
| `read_bars_adjusted(con, security_ids, as_of, ..., price_mode, snapshot_id)` | Like `read_bars_asof` with split adjustment | ✅ |
| `read_bars_latest(con, security_ids, ..., snapshot_id)` | Convenience — calls `read_bars_asof` with `now()` | ⚠️ Non-research |
| `read_panel(con, spine, as_of, dataset, snapshot_id)` | ASOF JOIN from spine (security_id + effective_date) | ✅ |
| `read_asof_join(con, spine, dataset, snapshot_id)` | Per-row PIT join with per-row `as_of` column | ✅ |

## Corporate Actions

| Function | Description |
|----------|-------------|
| `write_corp_actions(con, df)` | SCD2 insert with `compute_version_hash` |

## Indicators (derived)

| Function | Description |
|----------|-------------|
| `compute_indicator(con, security_id, indicator, as_of, ...)` | PIT-bounded indicator serving |

## Text Analytics (derived)

| Function | Description |
|----------|-------------|
| `get_text_items(con, security_id, as_of, ...)` | PIT-bounded news/social items |
| `annotate_text_items(df)` | Neutral NLP annotation (entities + sentiment) |

## Catalog & Health

| Function | Description |
|----------|-------------|
| `list_datasets(con)` | List all canonical tables with schema version and row count |
| `dataset_health(con, dataset)` | Per-dataset status, rows, latest date |
| `catalog_health(con)` | Overall catalog health: snapshot count, latest snapshot ID |
| `list_snapshots(con)` | List all DuckLake snapshots with timestamp and changes |
| `set_snapshot(con, snapshot_id)` | Pin reads to a specific DuckLake snapshot for reproducibility |
| `resolve_ingestion_run(con, run_id)` | Map ingestion_run_id to DuckLake snapshot ID |

## Dataset Read Pattern

All research readers follow this pattern:
1. Require explicit `as_of` parameter
2. Filter `available_at <= as_of`
3. Filter `effective_date <= as_of` (historical observation datasets)
4. Return newest version per natural key
5. Never default to `now()`

`latest_*` functions exist as explicit non-research convenience paths.
