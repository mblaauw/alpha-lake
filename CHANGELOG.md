# Changelog

All notable changes to Alpha-Lake are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
