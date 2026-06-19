# ADR-0020: Trading calendar and timezone policy

**Status:** Accepted

**Context:**
Alpha-Lake uses `effective_date` for valid time, freshness SLAs such as "available by next trading day," gap-fill detection, earnings sessions, and corporate-action ex-dates. All of these depend on a trading-calendar oracle and a timezone convention. Without an explicit policy, half-days, holidays, exchange-local closes, and UTC date boundaries can silently corrupt PIT reads and freshness checks.

**Decision:**
Use a pinned, vendored exchange-calendar oracle (initially `exchange_calendars`) for all exchange-session logic.

- All instants are stored UTC: `available_at`, `ingested_at`, `validated_at`, source publish instants, and DuckLake commit/system time. Enforced at the Polars normalize step (`pl.Datetime(time_zone="UTC")`) and DuckDB schema level (`TIMESTAMPTZ`). The Patito `BarFact` model accepts timezone-aware and timezone-naive datetimes; a runtime assertion in normalize ensures UTC.
- `effective_date` is the exchange-local session date resolved by the pinned calendar, not the UTC calendar date.
- Freshness checks that mention trading days use the dataset's exchange calendar.
- Gap-fill and backfill distinguish market-closed sessions from missing observations via the calendar.
- Calendar version is part of replay/config metadata so historical fixture expectations remain deterministic across calendar library updates. Implemented as `calendar_version` in `LakeConfig` and `CALENDAR_VERSION` in `calendar_.py`.

**Consequences:**
- Positive: PIT readers, freshness SLAs, gap-fill, and corporate-action semantics use one date oracle.
- Positive: Half-days and holidays no longer appear as missing data.
- Positive: UTC storage avoids ambiguous instants and daylight-saving edge cases.
- Negative: Calendar updates become compatibility-affecting inputs and must be pinned/vendored.
- Negative: Multi-exchange datasets need exchange-aware calendar selection per security or dataset.

**References:**
- DESIGN.md §4, §9, §13, §19, §26
- Related issue: #135

**Date:** 2026-06-19
