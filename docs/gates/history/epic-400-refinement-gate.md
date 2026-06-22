# Refinement Gate: Epic #400 → (next epic)

**Status:** Assessment complete — epic closing
**Last assessed:** 2026-06-22

## Child Issue Audit

| # | Title | PR | Status |
|---|-------|----|--------|
| 401 | API key configuration & documentation | #408 | Merged |
| 402 | FRED live ingestion | #409 | Merged |
| 403 | Finnhub live ingestion | #410 | Merged |
| 404 | Marketaux live ingestion | #411 | Merged |
| 405 | FMP + other sources live ingestion | #412 | Merged |
| 406 | Integration test harness | #413 | Merged |
| 407 | Operational readiness | #414 | Merged |

All 7 sub-issues completed and merged.

## Gate Checklist

### Functional completeness

- [x] API keys documented in `.env.example` and `docs/api-keys.md`
- [x] FRED keyless macro_series ingestion working end-to-end
- [x] Finnhub news, sentiment, insider_tx ingestion working (keyed)
- [x] Marketaux news + entity-level sentiment ingestion working (keyed)
- [x] StockTwits keyless sentiment ingestion working
- [x] ApeWisdom attention_metrics pipeline wired (API returns data)
- [x] FMP economic_calendar + analyst_estimates pipelines wired (require paid plan)
- [x] Generic `ingest_dataset()` flow supporting all dataset types
- [x] Dataset-specific normalize functions for each JSON shape
- [x] Table alias mapping (news→news_articles, sentiment→sentiment_annotations)
- [x] Integration test harness with fixture caching
- [x] Production deployment documentation

### API key status

- 5 keyless sources: FRED, SEC, StockTwits, ApeWisdom, Tiingo news
- 4 keyed sources: Finnhub, Marketaux, EODHD, FMP (FMP requires paid plan)
- Rest: missing keys, disabled or fallback

### Test coverage

- [x] `just test` passes: 237/238 (1 pre-existing infra DNS failure)
- [x] `just lint` clean
- [x] Forbidden-token grep clean
- [x] 12 live API tests created (skipped by default, run with `--run-live`)
- [ ] Live tests pass with all API keys configured (manual step)

### Development notes

- Finnhub uses `token` query param auth (not Bearer) — custom client needed
- FRED keyless path required CSV→JSON conversion in connector
- Marketaux requires explicit `--source marketaux` when precedence lists Finnhub first
- FMP free tier endpoints (`/v3/economic-calendar`, `/v3/analyst-stock-recommendations`) are legacy and return 403
- ApeWisdom uses `/filter/all-stocks/` (paginated) not the per-ticker endpoint
