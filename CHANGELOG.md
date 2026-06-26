# Changelog

All notable changes to Alpha-Lake are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

_(none yet)_

### Fixed

_(none yet)_

## [v0.1.0-alpha.3] — 2026-06-25

### Added

- **Alpha Vantage integration** — new multi-dataset source across 10 endpoint categories:
  - Fundamentals: INCOME_STATEMENT, BALANCE_SHEET, CASH_FLOW, OVERVIEW, SHARES_OUTSTANDING (#505–#507)
  - Corporate actions: DIVIDENDS, SPLITS (#508)
  - Insider transactions: INSIDER_TRANSACTIONS (#511)
  - Institutional holdings: INSTITUTIONAL_HOLDINGS (#512)
  - Economic indicators: 15 series including GDP, CPI, treasury yields, unemployment (#513)
  - Commodities: 11 series including WTI, Brent, natural gas, copper, grains (#514)
  - Top gainers/losers: TOP_GAINERS_LOSERS (#515)
  - ETF profiles: ETF_PROFILE (#516)
  - IPO calendar: IPO_CALENDAR (#517)
  - Listing status: LISTING_STATUS (#518)
  - New models: `InsiderTransactionFact`, `InstitutionalHoldingFact`, `TopMoverFact`,
    `ETPProfileFact`, `IPOEventFact`
  - See docs/adr/2026-06-25-alpha-vantage-integration.md for full architecture
- **Tiingo fundamentals connector** — switched from `/daily` (daily metrics) to
  `/statements` endpoint (financial statement line items). Added
  `fundamentals_from_json()` normalize function to transform Tiingo statements
  data into `FundamentalFact`-shaped rows.
- **Finnhub connector** — fixed `analyst_estimates` endpoint from broken
  `/stock/recommendation-trends` (302/404) to `/stock/recommendation` (200).
- **Earnings calendar** — replaced dead EODHD `/eod/earn-calendar` endpoint
  (404) with Finnhub `/calendar/earnings` connector. Added
  `earnings_calendar_from_finnhub()` normalize function.
- **Fundamentals P0 fixes** — wall-clock fallback removal, overview ID registry,
  threshold scale correction, TTM consecutive-quarter validation, N/M display,
  glossary tooltips, relative valuation context profile, peer-percentile downgrade (#500/#502)
- **Golden replay** — fixtures and replay tests for indicators, readouts, and
  fundamental metrics (bars + compute + estimate metrics)

### Fixed

- **Syntax error** — `except ExcType, var:` (Python 2 style) in `_shared.py`
  and `alphav.py` normalize, fixed to `except (ExcType, var):`
- **SEC EDGAR** — currently blocked (403); documented as dead, Tiingo recommended
- **EODHD** — earnings_calendar endpoint returns 404 (dead); replaced with Finnhub

### Added

- **Fundamental metrics** — canonical fundamentals dataset from SEC EDGAR
  Companyfacts with Patito model, tri-temporal Parquet storage, and SCD2
  versioning (#477 + #480)
- **Fundamental serving reader** — `read_fundamentals_asof()` with period-metric
  aggregation (TTM rollup, MRQ pass-through) and read-time valuation (P/E, P/S,
  P/FCF) composing price with per-share denominators (#480)
- **Fundamentals glossary** — `FundamentalGlossaryEntry` + `FUNDAMENTAL_GLOSSARY`
  registry with 27 metric definitions across 6 categories, 15 threshold profiles,
  state-resolution engine, and glossary JSON API (#481)
- **Fundamentals REST endpoints** — `GET /v1/fundamentals/metrics` (authenticated,
  PIT-safe) and `GET /v1/fundamentals/glossary` with optional `include` param
  for inputs/definitions/provenance (#483)
- **Fundamentals dashboard endpoints** — `GET /v1/dashboard/symbol/{symbol}/fundamentals`
  and `GET /v1/dashboard/fundamentals/glossary` (dashboard-gated, no auth) (#483)
- **Lake Watch Fundamentals tab** — category-grouped metric cards, symbol selector,
  pin/unpin with independent `lw_fund_pins` storage, glossary tooltips, and
  `latest=true` toggle (#485)
- **Symbol Readouts** — neutral interpretation layer over bars and technical
  indicators. 18 readouts across 7 categories: price action, trend, momentum,
  volatility, participation, relative strength, market regime (#447)
- **Readout definitions** — `ReadoutDefinition` dataclass + `READOUTS` registry
  with metadata (category, surface, formula, display hints) (#448)
- **Threshold profiles** — versioned TOML profiles (discrete, percentile,
  combined) + `resolve_state()` with insufficient-history guard (#449)
- **Readout computation** — 18 pure compute functions + `compute_all_readouts()`
  orchestrator with source-requirement gating (#450)
- **Readout REST endpoint** — `GET /v1/dashboard/symbol/{symbol}/readouts`
  with `as_of`, `latest`, `categories`, `readout_ids` params (#451)
- **ReadoutsConfig model** — typed `ReadoutsConfig` in config.py with
  profile_file, benchmark_symbol, phases fields (#451)
- **Interpretation test suite** — 52 tests covering all 18 readout functions,
  threshold profiles, orchestrator, determinism, and edge cases (#452)

### Fixed

- **Critical: `_match_zone` falsy-`min` bug** — `min=0.0` was treated as falsy
  and replaced with `-inf`, breaking the "range" zone in `breakout_state_v1`
  profile (#453)
- **Critical: MACD cross indicator fallback** — `macd_ema=0.0` was treated as
  falsy, falling through to `macd_signal` and producing spurious cross
  detection (#453)
- **Critical: Overlapping threshold zones** — `directional_bias_v1`,
  `macd_cross_v1`, and `momentum_quality_v1` zones overlapped at exactly 0.0,
  making neutral/mixed states unreachable (#453)
- **High: NaN/Inf propagation in `_last_or_none`** — helper functions passed
  NaN/Inf as valid floats through to state resolution, silently producing
  incorrect results (#453)
- **High: NaN/Inf in momentum quality** — `close / close.shift(10)` could
  produce NaN via zero-divide, not caught by `is None` guard (#453)
- **Medium: Bollinger width `"unavailable"` mislabeled as `"quiet"`** —
  unguarded attention/risk fallback for unavailable state (#453)
- **Medium: Percentile matching falsy-`percentile` bug** — `min_percentile=0.0`
  / `max_percentile=0.0` treated as falsy in `_matches_percentile` (#453)
- **Low: Dashboard category filter sentinel** — `ReadoutDefinition` class
  returned as sentinel instead of None when definition_id missing (#453)
- **I5/I7 violation: wall-clock fallback in `_make_obs`** — removed
  `datetime.now(UTC)` default from `_make_obs`; `as_of` is now a required
  keyword-only parameter for determinism in the interpretation layer
- **I5/I7 violation: wall-clock fallback in `compute_indicators`** — made
  `as_of` a required parameter; CLI now passes `get_clock().now()` explicitly
- **Falsy guard in `event_aggregations.py`** — `sum() or 0` replaced with
  explicit `None` check to distinguish "no data" from "genuine zero"
- **SQL injection in `kernel/__init__.py`** — replaced string concatenation in
  INSERT with parameterized `executemany()` for `_kernel_source_priority`
- **Stale config field** — removed unused `endpoint_override` from
  `SourceDatasetConfig` in config.py
- **Dead exports** — removed unused `CATEGORIES` and `readouts_by_category`
  from interpretation `__all__`
- **DESIGN.md drift** — fixed 6 stale references (`indicators/` → `indicators.py`,
  `text/` → `derived/`, `dlt` reference, `SQLMesh` references, `assets.py` →
  `dagster_assets.py`)
- **Typo in conftest.py** — fixed `# ty: ignore` → `# type: ignore`
- **Debug print in fixtures** — replaced `print()` with `cli_ui.info()`
- **Container profile path** — added `config/` COPY to Dockerfile so
  `config/threshold_profiles.toml` is found at runtime
- **String→float crash in readouts** — `_build_indicator_dict` no longer attempts
  to `float()` metadata columns (`security_id`, timestamps, etc.)
- **`/v1/bars/indicators` datetime crash** — fixed datetime→JSON serialization bug
  (same fix applied to both authenticated and dashboard routers)
- **`price_mode` 500→422** — added input validation for `price_mode` parameter;
  invalid values now return 422 instead of crashing with 500
- **Dead `sec_id is None` guards removed** — 6 endpoints had unreachable 404
  checks; `resolve_security()` always returns a string
- **Dead `return_126`/`return_252` mappings removed** — unreachable entries in
  `_store_indicators_into`
- **`search_securities()` now has `lake_bars` fallback** — when `security_master`
  is empty, falls back to scanning `lake_bars` for matching security IDs
- **Missing `corp_actions` table handled** — `read_bars_adjusted` falls back to
  raw bars when `corp_actions` doesn't exist
- **Shared serialization helper** — extracted `_serialize_bars_df()` into
  `_shared.py` so both routers share the same datetime/numeric conversion logic
- **Frontend redesign** — replaced htmx-based SPA with Vanilla JS SPA;
  FT salmon-paper design system (light-first); 6 nav tabs; SVG charts;
  AS OF popup control; readout cards with tooltip glossary; sentiment
  leaderboard; indicator tiles with pin/unpin; PIT playground; removed
  service-worker.js (PWA dropped); added icons/

## [v0.1.0-alpha.2] — 2026-06-24

### Added

- **80+ Technical Indicators** — SMA, EMA, RSI, MACD, Bollinger, ATR, OBV, VWAP,
  ADX, Aroon, CCI, stochastic, Keltner, Donchian, WMA, KAMA, beta, alpha,
  relative strength, correlation, and more (#435)
- **Batch compute engine** — `compute_all_indicators()` single-pass pipeline
  reusing intermediates across all indicators
- **Indicator glossary** — machine-readable `_glossary.py` (96 entries) + API
  endpoint + dashboard tooltip lookup
- **Dashboard endpoints** — `/bars/summary`, `/attention/leaderboard`,
  `/macro/{series_id}`, `/insider/{symbol}`, `/analyst/{symbol}`
- **Lake Watch dashboard** — SPA with Overview, Bars, Dataset, Security, PIT
  tabs, indicator overlays, as_of scrubber, price_mode toggle, PWA support
- **Live data ingestion** — EODHD (3034 real bars), Finnhub, Marketaux, FRED,
  FMP, Tiingo pipelines with real API keys (#400)
- **Integration test harness** — live API tests with fixture caching (#406)
- **Idempotent ingestion** — skip API calls when data already exists
- **Dataset contracts** — 10 YAML contract files in `contracts/`
- **Multi-cohort ApeWisdom ingestion** — 20 cohort channels

### Changed

- **Dashboard restyle** — warm-tone, newsroom-style design, dark/light theme,
  segment pill tabs, serif wordmark, card grid, iOS rows
- **PIT reader / serving kernel** — versioned SQL macros, source precedence,
  descriptor-derived DDL generation
- **price_mode toggle** — wire split-adjusted prices through `/bars` and
  `/bars/summary` (total_return deferred to future kernel work)

### Fixed

- **EODHD API format** — added `fmt=json` param (was defaulting to CSV)
- **pytz dependency** — added for DuckDB TIMESTAMPTZ deserialization
- **Connection leaks** — shared connection singleton with auto-reconnect
- **Synthetic data isolation** — `"demo"` source_id for all demos
- **Forbidden tokens** — renamed `bullish`/`bearish` variables in indicator code
- **Endpoint + GUI deep sweep** — removed dead code, fixed timezone bug in as_of
  input, added indicator results cache, fixed `security_detail` default
- **Non-UI code deep sweep** — added PIT `as_of` filters, removed dead constants
  (`_SPY_SECURITY_ID`, `_REVERSE_INDICATOR_MAP`), hoisted inner functions,
  fixed docstring drift

## [v0.1.0-alpha.1] — 2026-06-21

### Added

- **Tri-temporal lake architecture** — raw archive, canonical storage, point-in-time reads
- **DuckDB engine** with DuckLake catalog extension, Postgres catalog, RustFS (S3) blob store
- **Connector framework** — httpx + tenacity, rate-limit budgeting, keyed and keyless sources
- **SEC EDGAR insider transactions** — full ticker→CIK resolution
- **Congress trading dataset** — `congress_trades` connector + Patito model
- **Analyst estimates dataset** — `analyst_estimates` connector + Patito model
- **Macro series dataset** — `macro_series` FRED connector with vintage-preserving pipeline
- **Economic calendar dataset** — `economic_calendar` connector
- **News articles + sentiment annotations** — Finnhub, Marketaux, StockTwits pipelines
- **Attention metrics** — ApeWisdom social attention with cohort support
- **Patito fact models** — schema-as-validator for all datasets
- **Versioned SQL kernel** — PIT resolution macros, source precedence
- **REST transport layer** — FastAPI, API key auth, token bucket rate limiting
- **Deterministic golden replay** — property tests, fixture freezing, Hypothesis
- **Docker Compose stack** — app, postgres, rustfs, DuckLake
- **Air-gap deployment** — `just vendor` for offline wheelhouse + images
- **CLI** — Typer-based: ingest, serve, health, dataset, bootstrap commands
- **Config system** — TOML-based `RootConfig` with env var overrides
- **Secret store** — `EnvSecretStore` / `StaticSecretStore` ABC
- **Layer architecture** — import-linter contract enforcement
- **Documentation** — DESIGN.md, operations.md, ADR catalog, skills index

### Fixed

- Deep sweep: 3 critical bugs, 4 config inconsistencies (#374)
- Health checks use host-override env vars
- DuckDB-Polars interop (removed `to_arrow()` calls)

[Unreleased]: https://github.com/mblaauw/alpha-lake/compare/v0.1.0-alpha.3...HEAD
[v0.1.0-alpha.3]: https://github.com/mblaauw/alpha-lake/compare/v0.1.0-alpha.2...v0.1.0-alpha.3
[v0.1.0-alpha.2]: https://github.com/mblaauw/alpha-lake/compare/v0.1.0-alpha.1...v0.1.0-alpha.2
[v0.1.0-alpha.1]: https://github.com/mblaauw/alpha-lake/releases/tag/v0.1.0-alpha.1
