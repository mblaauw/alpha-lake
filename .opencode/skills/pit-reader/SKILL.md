---
name: pit-reader
description: Alpha-Lake point-in-time reader and ASOF JOIN template. Use when implementing as_of reads, panels, spine joins, latest paths, or serving readers.
---

# PIT Reader

This is invariant-dense. Prefer stronger model or cross-check with `alpha-lake-invariants` skill for substantive changes.

## Rules

- Research readers require `as_of`.
- Every row satisfies `available_at <= as_of`.
- Historical observations also satisfy `effective_date <= as_of`.
- Known-future event datasets may expose future event dates only if `available_at <= as_of`.
- Stage 1 selects newest version per source; Stage 2 applies dataset-specific source precedence.
- `latest_*` is a separate PIT-unsafe API and still filters `available_at <= now()`.

## ASOF JOIN Shape

```sql
WITH spine AS (
  SELECT security_id, effective_date, as_of
  FROM requested_spine
), per_source AS (
  SELECT s.*, b.* EXCLUDE (security_id, effective_date)
  FROM spine s
  ASOF JOIN bars b
    ON s.security_id = b.security_id
   AND s.effective_date = b.effective_date
   AND s.as_of >= b.available_at
  WHERE b.effective_date <= s.as_of
), preferred AS (
  SELECT *, row_number() OVER (
    PARTITION BY security_id, effective_date, as_of
    ORDER BY dataset_source_priority ASC
  ) AS source_rank
  FROM per_source
)
SELECT * EXCLUDE (source_rank)
FROM preferred
WHERE source_rank = 1;
```

## Leakage Fixture

```text
fact effective_date=2026-06-01 available_at=2026-06-10 value=2
fact effective_date=2026-06-01 available_at=2026-06-02 value=1
read as_of=2026-06-05 -> value=1
read as_of=2026-06-11 -> value=2
```

## Gates

```bash
rg -n "as_of\s*=\s*None|available_at\s*>|latest" src/alpha_lake/serving src/alpha_lake/catalog
rg -n "row_number\(\).*available_at" src/alpha_lake/serving src/alpha_lake/catalog
just lint
```

## Forbidden

- Do not make `as_of` optional on research readers.
- Do not collapse sources before version selection.
- Do not use system time/DuckLake snapshot as PIT boundary.
- Do not expose latest results without PIT-unsafe marker.
