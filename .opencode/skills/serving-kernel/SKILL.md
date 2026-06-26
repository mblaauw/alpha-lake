---
name: serving-kernel
description: Alpha-Lake versioned SQL kernel — register_kernel, kernel/sql/*.sql, source precedence macros, descriptor-derived stubs. Use when adding or modifying PIT resolution macros, kernel SQL files, or the kernel registration path.
---

# Serving Kernel

The kernel is a versioned SQL artifact in `src/alpha_lake/kernel/sql/`. Each dataset contract produces one `.sql` file defining a `CREATE OR REPLACE MACRO ... AS TABLE`.

## Architecture

```
kernel/sql/*.sql       — PIT resolution table macros
kernel/__init__.py     — register_kernel(con) loader
serving/__init__.py    — thin Python callers binding params → kernel macros
transport/             — FastAPI REST, Python library, CLI harness
```

## Rules

- Kernel SQL is **PIT/precedence resolution logic only**. Lookback caps, auth, rate limiting live in transport.
- Each dataset contract produces one `.sql` file named `<dataset>_pit.sql` (or `<dataset>_pit_<variant>.sql`).
- Currently defined macros:
  - `bars_pit` / `bars_asof` — bar data PIT resolution
  - `bars_pit_adjusted` / `bars_adjusted_asof` — split-adjusted bar PIT
  - `bars_pit_join` / `bars_asof_join` — ASOF join across securities
  - `bars_pit_spine` / `bars_asof_spine` — calendar-spined panel reads
  - `fundamental_metrics_pit` / `fundamental_metrics_asof` — fundamentals PIT
- Macros are loaded per-connection by `register_kernel(con)`, called inside `catalog.connect()` — every transport gets them automatically.
- SQL files are cached at import time (`_SQL_FILES` in `kernel/__init__.py`) so `register_kernel` avoids disk reads.

## Source Precedence Pattern

```sql
CREATE OR REPLACE MACRO bars_asof(p_security_ids, p_as_of, p_start_date, p_end_date) AS TABLE (
    SELECT b.* EXCLUDE (source_priority_rank)
    FROM (
        SELECT b.*,
               ROW_NUMBER() OVER (
                   PARTITION BY b.security_id, b.effective_date
                   ORDER BY COALESCE(p.priority, 999), b.available_at DESC
               ) AS source_priority_rank
        FROM lake_bars b
        LEFT JOIN _kernel_source_priority p
            ON p.dataset = 'bars_daily' AND p.source_id = b.source_id
        WHERE list_contains(p_security_ids, b.security_id)
          AND b.available_at  <= p_as_of::TIMESTAMPTZ
          AND b.effective_date <= p_as_of::DATE
          AND (p_start_date IS NULL OR b.effective_date >= p_start_date::DATE)
          AND (p_end_date   IS NULL OR b.effective_date <= p_end_date::DATE)
    ) b
    WHERE source_priority_rank = 1
    ORDER BY b.security_id, b.effective_date
);
```

Key points:
- `COALESCE(priority, 999)` — unknown sources fall to lowest precedence.
- `available_at DESC` — within same priority, newest knowledge wins.
- `LEFT JOIN _kernel_source_priority` — kernel reads precedence from config-driven table, never hardcoded.
- Macro returns a TABLE — callable as `SELECT * FROM bars_asof(?, ?, ?, ?)`.

## Registering a New Dataset Macro

1. Create `<dataset>_pit.sql` in `kernel/sql/` following the precedence pattern above.
2. In `kernel/__init__.py`, add `generate_ddl(DatasetModel, "lake_<dataset>")` inside `register_kernel` if the table schema needs a stub for compile-time resolution.
3. Tests: verify macro against fixture tables with known precedence. See `tests/unit/test_kernel.py`.

## Per-Row PIT (ASOF JOIN)

For spine mode (per-row `as_of`), the kernel uses DuckDB's `ASOF JOIN`:

```sql
CREATE OR REPLACE MACRO bars_asof_join() AS TABLE (
    WITH base AS (
        SELECT ...,
               ROW_NUMBER() OVER (
                   PARTITION BY s.security_id, s.effective_date, s.as_of
                   ORDER BY COALESCE(p.priority, 999), b.available_at DESC
               ) AS rn
        FROM _spine s
        LEFT JOIN lake_bars b
            ON s.security_id = b.security_id
           AND b.effective_date <= s.effective_date
           AND b.available_at <= s.as_of
        LEFT JOIN _kernel_source_priority p ON ...
    )
    SELECT * EXCLUDE (rn) FROM base WHERE rn = 1
);
```

The `_spine` view is registered by the serving layer before calling the macro.

## Forbidden

- Do not embed REST-layer concerns (auth, rate limit, lookback cap) in kernel SQL.
- Do not write kernel macros that accept `as_of = NULL`.
- Do not hardcode source priority in SQL — always use `_kernel_source_priority`.
- Do not use system time (`now()`, `current_timestamp`) inside kernel macros — PIT comes from the caller's `as_of`.

## Gates

```bash
rg -n "now\(\)|current_timestamp|CURRENT_TIMESTAMP" src/alpha_lake/kernel/sql/
rg -n "max_lookback|rate_limit|api_key" src/alpha_lake/kernel/
just lint
```
