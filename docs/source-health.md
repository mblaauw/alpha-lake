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
|---|---|---|---|---|
| EODHD | `https://eodhd.com/api` | live | 2026-06-21 | Primary bars source. API key required. |
| Tiingo | `https://api.tiingo.com` | live | 2026-06-21 | Secondary bars, fundamentals, news. |
| Alpaca | `https://data.alpaca.markets` | live | 2026-06-21 | Tertiary bars. Disabled by default. |
| SEC EDGAR | `https://data.sec.gov` | live | 2026-06-21 | Fundamentals + insider filings. UA required. |
| OpenFIGI | `https://api.openfigi.com/v3` | live | 2026-06-21 | Identifier resolution. |
| FRED | `https://api.stlouisfed.org/fred` | live | 2026-06-21 | Macro series. Keyless fallback available. |
| FMP | `https://financialmodelingprep.com/stable` | live (paid) | 2026-06-21 | Economic calendar + analyst ratings. Requires paid plan. |
| Finnhub | `https://finnhub.io/api/v1` | live | 2026-06-21 | News, analyst estimates, insider sentiment. |
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

## Deprecated Sources

| Source | Reason | Removed |
|---|---|---|
| *(none currently)* | | |
