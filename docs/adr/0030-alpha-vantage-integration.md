# ADR-0030: Alpha Vantage Multi-Dataset Integration

**Date:** 2026-06-25
**Status:** Accepted

## Context

Alpha-Lake needs a free-tier, single-API-key data source that covers multiple
dataset categories to fill gaps and provide secondary fallback sources. Existing
sources each cover narrow domains (Tiingo: fundamentals, Finnhub: estimates,
FRED: macro) and some have endpoint rot (EODHD earnings calendar 404, SEC
EDGAR blocking automated tooling).

Alpha Vantage provides a single API key with access to 50+ endpoint categories
across fundamentals, corporate actions, insider transactions, institutional
holdings, economic indicators, commodities, and market data — all on a free
tier (25 calls/day, 5 calls/min).

## Decision

Integrate Alpha Vantage as a multi-dataset source using a single connector
module with per-endpoint fetch functions.

## Architecture

### Connector design

All AV endpoints share the same base URL (`https://www.alphavantage.co/query`)
and authentication (`?apikey=XXX`). The connector module
(`src/alpha_lake/connectors/alphav.py`) exposes separate fetch functions per
dataset category, each calling the appropriate AV `function` parameter.

To manage the free-tier rate limit (25 calls/day), the fundamentals connector
batches 7 related calls (IS + BS + CF + OVERVIEW + SHARES + EARNINGS +
EARNINGS_ESTIMATES) into a single `fetch_fundamentals()` call with 12-second
delays between internal requests.

### Data flow

AV functions are mapped to existing Alpha-Lake datasets where possible:

| AV function | Alpha-Lake dataset | Record type |
|---|---|---|
| INCOME_STATEMENT, BALANCE_SHEET, CASH_FLOW | `fundamentals` | FundamentalFact |
| OVERVIEW, SHARES_OUTSTANDING, EARNINGS | `fundamentals` | FundamentalFact |
| DIVIDENDS, SPLITS | `corp_actions` | CorpActionFact |
| INSIDER_TRANSACTIONS | `insider_transactions` | InsiderTransactionFact |
| INSTITUTIONAL_HOLDINGS | `institutional_holdings` | InstitutionalHoldingFact |
| REAL_GDP, CPI, TREASURY_YIELD, etc. | `macro_series` | MacroSeriesFact |
| WTI, BRENT, NATURAL_GAS, etc. | `macro_series` | MacroSeriesFact |
| TOP_GAINERS_LOSERS | `top_movers` | TopMoverFact |
| ETF_PROFILE | `etf_profiles` | ETPProfileFact |
| IPO_CALENDAR | `ipo_calendar` | IPOEventFact |

### Source precedence

For `fundamentals`, AV is a secondary source after Tiingo:
```toml
[precedence.fundamentals]
sources = ["tiingo", "alphav"]
```

### Rate limit management

The free tier allows 25 calls/day and 5 calls/min. The connector uses
`asyncio.sleep(12)` between calls to stay under the per-minute limit.
Per-day limits are enforced by `check_budget()`.

### New datasets registered

Five new datasets were registered in `DATASETS`:
- `insider_transactions` — per-executive buy/sell events
- `institutional_holdings` — 13F holder snapshots
- `top_movers` — daily gainers/losers/most-active
- `etf_profiles` — ETF metadata and holdings
- `ipo_calendar` — upcoming IPO events

## Consequences

### Positive

- Single API key provides access to 10+ dataset categories
- Free tier eliminates cost barrier for development/CI
- Common response format simplifies normalize functions
- Precedence ensures AV fills gaps without replacing primary sources

### Negative

- 25 calls/day limit requires careful orchestration (~3 full symbol refreshes)
- `INDEX_DATA` endpoints are premium-gated (no free index OHLC)
- Rate limit resets at midnight ET, not UTC
- Per-call latency is higher due to 12-second spacing between batch calls

### Mitigations

- Precedence ordering minimizes AV usage (primary sources are tried first)
- Batch fetching groups multiple endpoints into single ingest calls
- Idempotency guard prevents re-fetching unchanged data
