# ADR-0010: Flow functions; Typer CLI first, Dagster optional later

**Status:** Accepted

**Context:** Pipeline logic should be callable from CLI, test harness, and Dagster without duplication.

**Decision:** All pipeline logic lives once in `flows/`. Typer CLI inside the app container is the first operational shell. Dagster is added later as an optional thin shell over `flows/`, never owning business logic.

**Consequences:**
- Positive: Single source of pipeline logic
- Positive: CLI proves vertical slice against real stack before Dagster complexity
- Negative: Dagster integration must be retrofitted

**References:**
- DESIGN.md §19, §28 Phase 6

**Date:** 2026-06-18
