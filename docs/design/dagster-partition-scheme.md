# Dagster Partition Scheme

## Partition Key

Each Dagster partitioned asset maps to one DuckLake write target. The partition key is:
`(dataset, effective_date_bucket[, security_range])`

- `dataset`: the canonical dataset name (e.g. `lake_bars`, `fundamentals`)
- `effective_date_bucket`: monthly or daily bucket of `effective_date`
- `security_range`: optional hash-based security range for large datasets

## One Writer Per Partition

DuckLake's MERGE INTO does not support multiple concurrent writers on the same table.
The partition scheme guarantees structural write-contention avoidance: each partition maps
to exactly one Dagster partition, and Dagster ensures serial execution within a partition.

## Mapping to Dagster Assets

```python
@dg.asset(
    partitions_def=MonthlyPartitionsDefinition(start_date="2020-01-01"),
    group_name="bars",
)
def bars_daily(context: dg.AssetExecutionContext):
    partition_date = context.partition_key
    # Ingest bars for this month
```

## Retry Strategy

- On failure: retry 3 times with exponential backoff (1s, 4s, 16s)
- Boundary overlaps: if two partitions cover overlapping date ranges, the last-writer
  wins for each (security_id, effective_date, available_at) tuple via MERGE INTO dedup
- Idempotent: re-running a failed partition is safe because MERGE INTO is idempotent
