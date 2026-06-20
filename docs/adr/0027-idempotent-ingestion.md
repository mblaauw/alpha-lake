# ADR-0027: Idempotent Ingestion — skip existing data before API calls

**Status:** Accepted

**Context:**
Every `ingest` or `backfill` invocation called the upstream connector (EODHD, Tiingo, Reddit, ...) or regenerated synthetic data for the full requested date range, regardless of whether the canonical table already held the same facts. This had three costs:

1. **API waste.** Repeated calls for already-collected historic data consumed API quota, triggered rate limits, and slowed re-runs.
2. **Bitemporal version noise.** Each re-ingest inserted a new `available_at` version of identical facts, bloating the table and requiring compaction.
3. **Slow iteration.** During development and testing, restarting a pipeline re-fetched every security_id's entire history rather than only the missing slice.

The data itself is immutable once a trading day has passed — bars, corporate actions, fundamentals, and insider transactions do not change retroactively. Re-fetching them is never useful.

**Decision:**
Before every connector call or synthetic-data generation, query the canonical table for existing rows matching the requested date range and security. Three outcomes:

1. **Fully covered** — every date in the requested range already has a row → skip entirely, return 0.
2. **Partially covered** — some dates exist, some don't → narrow the range to only the missing dates and pass the narrowed `(from, to)` to the connector.
3. **No coverage** — no data exists → proceed with the original range.

The check is implemented as a single helper function:

```python
def _missing_dates(
    con: duckdb.DuckDBPyConnection,
    table: str,
    sid: str,
    from_date: str = "",
    to_date: str = "",
) -> list[str]:
```

`_missing_dates` queries `SELECT DISTINCT effective_date` on the target table, computes the set difference against the requested range, and returns the missing dates as a sorted list of ISO strings. An empty list means "skip."

The helper handles two edge cases:
- **Table doesn't exist yet** — catches `duckdb.CatalogException` and treats it as "no coverage."
- **No date bounds provided** — checks for *any* existing data for the security. If data exists returns `[]` (skip). If the table is empty returns `[<today>]` so the ingestion produces at least a single-row fixture for today.

**Implementation scope (Epic #344):**

| Dataset | Key column(s) | Coverage strategy | Status |
|---|---|---|---|
| `lake_bars` | `security_id + effective_date` | date-range narrowing | Implemented in `flows/__init__.py` |
| `corp_actions` | `security_id + effective_date + ...` | date-range narrowing | Helper available |
| `fundamentals` | `security_id + fiscal_period + ...` | date-range narrowing | Helper available |
| `insider_tx` | `security_id + effective_date + ...` | date-range narrowing | Helper available |
| `news_articles` | `article_id + source_id` | key-existence check (`SELECT 1 WHERE article_id = ?`) | Helper available for future use |
| `social_posts` | `post_id_hash + source_id` | key-existence check | Helper available for future use |

**Consequences:**
- *Positive:* Re-running `ingest AAPL 2026-01-01 2026-01-31` after a successful first run makes zero API calls and returns 0 immediately.
- *Positive:* `ingest AAPL 2026-01-01 2026-02-28` when Jan is already ingested only fetches Feb from the connector.
- *Positive:* The check is a single `DISTINCT effective_date` query on an indexed column — negligible cost per security.
- *Positive:* No new configuration or API surface. The behavior is automatic and transparent.
- *Positive:* The `_missing_dates` helper is re-usable by any future dataset that has `security_id + effective_date`.
- *Neutral:* `_missing_dates` only checks whole-calendar-day coverage, not business-day coverage. If a date is missing from the table but was a non-trading day (weekend/holiday), the connector call will return an empty response for that day and no row will be inserted. The next re-run will see the same date as "missing" again and re-call the connector. This is harmless but wastes one empty API call per non-trading day per re-run. A future improvement could integrate the trading calendar into the coverage check.
- *Negative:* None identified.
