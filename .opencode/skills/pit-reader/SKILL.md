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

## Kernel Macro Invocation

PIT resolution is a **versioned SQL kernel macro**, not inline Python SQL. Call the macro via `pit_read` or the specific reader functions in `src/alpha_lake/serving/`:

### Security-list mode (scalar `as_of`)

```python
con.execute("SELECT * FROM bars_asof(?, ?, ?, ?)", [security_ids, as_of, start_date, end_date])
```

The macro is defined in `src/alpha_lake/kernel/sql/bars_pit.sql` — it applies the two-stage resolution (newest version per source, then source precedence via `_kernel_source_priority`).

### Spine mode (per-row `as_of`)

```python
con.register("_spine", spine)     # spine has security_id, effective_date, as_of
con.execute("SELECT * FROM bars_asof_join()")
```

The `_spine` view is registered by the serving layer before calling the macro. The join macro is defined in `src/alpha_lake/kernel/sql/bars_pit_join.sql`.

### Scalar spine mode (single `as_of` on all rows)

```python
con.execute("SELECT * FROM bars_asof_spine(?)", [as_of])
```

Defined in `src/alpha_lake/kernel/sql/bars_pit_spine.sql`.

### Precedence Pattern (for reference)

```sql
ROW_NUMBER() OVER (
    PARTITION BY b.security_id, b.effective_date
    ORDER BY COALESCE(p.priority, 999), b.available_at DESC
)
```

See `serving-kernel` skill for the full macro definition and registration workflow.

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
- Do not hand-write PIT SQL in Python f-strings — always use kernel macros.
- Do not hardcode source priority — the kernel reads `_kernel_source_priority`.
