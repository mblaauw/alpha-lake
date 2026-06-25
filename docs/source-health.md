# Source Health

Registry of known data sources, their endpoints, and current operational
status. This file is the single source of truth for source availability.

## Status Legend

- **live** — endpoint is operational and actively maintained.
- **degraded** — endpoint responds but has reduced limits or stale data.
- **gated** — endpoint requires API key or approval beyond the free tier.
- **dead** — endpoint is non-functional; do not use.

## Sources

| Source | Endpoint | Status | Last Audited | Notes |
|---|---|---|---|---|---|
| EODHD | `https://eodhd.com/api` | gated | 2026-06-25 | Primary bars source. `earnings_calendar` endpoint returns 404 (dead). API key required. |
| Tiingo | `https://api.tiingo.com` | live | 2026-06-25 | Secondary bars, fundamentals (`/statements`), news. |
| Alpaca | `https://data.alpaca.markets` | live | 2026-06-21 | Tertiary bars. Disabled by default. |
| SEC EDGAR | `https://data.sec.gov` | dead | 2026-06-25 | Blocks automated tooling with 403. Send UA with contact email to unblock. |
| OpenFIGI | `https://api.openfigi.com/v3` | live | 2026-06-21 | Identifier resolution. |
| FRED | `https://api.stlouisfed.org/fred` | live | 2026-06-21 | Macro series. Keyless fallback available. |
| FMP | `https://financialmodelingprep.com/stable` | live (paid) | 2026-06-21 | Economic calendar + analyst ratings. Requires paid plan. |
| Finnhub | `https://finnhub.io/api/v1` | live | 2026-06-25 | News, analyst estimates (recommendation trends -> `/stock/recommendation`), earnings calendar (`/calendar/earnings`), insider sentiment. |
| Marketaux | `https://api.marketaux.com/v1` | live | 2026-06-21 | News + sentiment. Strict daily quota (100). |
| StockTwits | `https://api.stocktwits.com/api/2` | live | 2026-06-21 | Keyless social sentiment tags. |
| ApeWisdom | `https://apewisdom.io/api/v1.0` | live | 2026-06-21 | Keyless aggregated attention. |
| QuiverQuant | `https://api.quiverquant.com/beta` | live | 2026-06-21 | Congressional trades. Strict daily quota (100). |
| Reddit | `https://oauth.reddit.com` | degraded | 2026-06-21 | OAuth token refresh required periodically. |

## Brittle Fallbacks

The following connectors have fallback paths that are known to be brittle
and may produce ``quality_status = "quarantined"`` data:

- **congress_trades** (Quiver) — HTML scrape fallback; data quality is
  lower than the API path.
- **FRED** — CSV keyless fallback; parsable but unstructured.

## Deprecated / Dead Endpoints

| Endpoint | Reason | Replaced By |
|---|---|---|
| EODHD `/eod/earn-calendar` | Returns 404 (dead) | Finnhub `/calendar/earnings` |
| Finnhub `/stock/recommendation-trends` | Returns 302/404 (deprecated) | Finnhub `/stock/recommendation` |
| SEC EDGAR `/api/xbrl/companyfacts` | Blocks automated tooling with 403 | Tiingo `/tiingo/fundamentals/*/statements` |
