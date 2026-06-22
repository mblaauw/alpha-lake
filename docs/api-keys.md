# API Keys

Most Alpha-Lake sources require an API key. This guide explains how to obtain each key.

## Quick start

```bash
cp .env.example .env
# Edit .env and fill in the keys you need
```

Keys are read from environment variables prefixed with `ALPHA_LAKE_`. The `.env` file is
loaded automatically by the Docker Compose stack (see `compose.yaml`). For local runs,
export the variables or use a `.env` file in the working directory.

## Per-source instructions

### EODHD

1. Register at [eodhd.com](https://eodhd.com/register)
2. Verify email and log in
3. Go to **API Dashboard** — your API token is displayed
4. Set `ALPHA_LAKE_EODHD_API_KEY` in `.env`

Free tier: limited calls per day. Check your plan at eodhd.com.

### Tiingo

1. Register at [api.tiingo.com](https://api.tiingo.com/)
2. Verify email and log in
3. Go to **Account → API Token**
4. Set `ALPHA_LAKE_TIINGO_API_KEY` in `.env`

Free tier: yes, with daily limits.

### Alpaca

1. Register at [alpaca.markets](https://alpaca.markets/)
2. Create a paper trading account
3. Go to **Dashboard → API Keys**
4. Copy both **Key ID** and **Secret Key**
5. Set `ALPHA_LAKE_ALPACA_API_KEY_ID` and `ALPHA_LAKE_ALPACA_API_SECRET_KEY` in `.env`

Free tier: yes (paper trading environment).

### OpenFIGI

1. Register at [openfigi.com](https://www.openfigi.com/)
2. Go to your account dashboard
3. Copy your API key
4. Set `ALPHA_LAKE_OPENFIGI_API_KEY` in `.env`

Free tier: yes.

### Reddit

1. Go to [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps)
2. Click **Create App** or **Create Another App**
3. Choose **script** type
4. Copy the **client ID** (under the app name)
5. Set `ALPHA_LAKE_REDDIT_API_KEY` in `.env`

Free tier: yes (OAuth app credentials).

### Quiver Quantitative

1. Register at [quiverquant.com](https://www.quiverquant.com/)
2. Subscribe to a paid plan
3. Go to your account settings → API
4. Copy your API key
5. Set `ALPHA_LAKE_QUIVER_API_KEY` in `.env`

Note: Quiver is a paid-only service. No free tier available.

### Marketaux

1. Register at [marketaux.com](https://www.marketaux.com/)
2. Verify email and log in
3. Go to **Dashboard → API Keys**
4. Copy your API token
5. Set `ALPHA_LAKE_MARKETAUX_API_KEY` in `.env`

Free tier: 100 requests per day.

### Finnhub

1. Register at [finnhub.io](https://finnhub.io/)
2. Verify email and log in
3. Go to **Dashboard → API Key**
4. Copy your API key
5. Set `ALPHA_LAKE_FINNHUB_API_KEY` in `.env`

Free tier: 60 requests per minute. Some endpoints (e.g. real-time quotes) may be
restricted on the free plan.

### Financial Modeling Prep (FMP)

1. Register at [financialmodelingprep.com](https://financialmodelingprep.com/)
2. Verify email and log in
3. Go to **Dashboard → API**
4. Copy your API key
5. Set `ALPHA_LAKE_FMP_API_KEY` in `.env`

Free tier: 250 requests per day.

### SEC EDGAR (contact email, no key required)

SEC EDGAR requires a User-Agent header with a contact email. No API key is needed.

1. Set `ALPHA_LAKE_SEC_CONTACT_EMAIL` in `.env` (e.g. `your-name@example.com`)
2. The connector uses this email for the `User-Agent` header automatically

Without a contact email, SEC requests may be rate-limited or blocked.

## Sources that don't need keys

| Source | Reason |
|--------|--------|
| **FRED** (St. Louis Fed) | Public API; keyless fallback built in |
| **StockTwits** | Public API; no authentication required |
| **ApeWisdom** | Public API; no authentication required |
| **SEC** | Public data; contact email optional |

## Verifying key setup

Run `just health` to check which sources have valid API keys configured:

```bash
$ just health
✓ FRED — configured (keyless)
✓ SEC — configured (keyless)
✓ Finnhub — configured (keyed)
✗ Marketaux — missing API key
```

## Rate limits

Each source's rate limits are configured in `config/stack.toml` under `[sources.<id>]`:

| Source | Rate limit (sec) | Rate limit (min) | Rate limit (day) | Max retries |
|--------|------------------|------------------|------------------|-------------|
| EODHD | 10/s | — | 1000/day | 3 |
| Tiingo | 0.5/s | 30/min | 500/day | 3 |
| Alpaca | 1/s | 200/min | — | 3 |
| SEC | 10/s | — | — | 5 |
| OpenFIGI | 0.33/s | 20/min | — | 3 |
| Reddit | 1/s | 10/min | — | 3 |
| StockTwits | 1/s | — | — | 3 |
| ApeWisdom | 1/s | — | — | 3 |
| Quiver | 1/s | — | 100/day | 3 |
| Marketaux | 1/s | — | 100/day | 3 |
| Finnhub | 1/s | 55/min | — | 3 |
| FMP | 5/s | — | 250/day | 3 |
| FRED | 5/s | — | 120000/day | 3 |

Rate-limit budgets are enforced client-side; hitting the daily quota produces a
`data_gap` outcome rather than a hard failure.
