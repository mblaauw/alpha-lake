# ADR-0017: Derived technical indicator library (neutral, PIT-bounded, cacheable)

**Status:** Accepted

**Context:**

The lake ingests and canonicalizes raw OHLCV bars, corporate actions, and security master data. Every downstream consumer who wants to compute technical indicators (moving averages, momentum, volatility, bands, volume metrics) must reimplement the same calculations from scratch, with no shared library, no PIT-boundary enforcement, and no way to avoid redundant computation across strategies.

ADR-0009 established the principle that the lake stores raw facts and provides a transform library, never a feature store with strategy-semantic materialization. However, the scope of that transform library was left unspecified (EMA, ATR, rolling volume only) and explicitly excluded a materialized cache.

We now need a comprehensive, library-grade indicator system that:

- Covers the full range of commonly-used technical indicators across 12 categories (price transforms, returns, moving averages, trend, momentum, volatility, bands/channels, volume, range/breakout, risk/statistics, support/resistance, candlestick facts, relative strength, calendar metadata).
- Enforces PIT boundaries automatically: every indicator value is bounded by `as_of`.
- Allows an optional materialized cache for performance, without compromising the canonical-truth principle.
- Draws a clean boundary: neutral measurements vs strategy interpretation.

**Decision:**

Alpha-Lake ships a comprehensive technical indicator library that is:

1. **Parameterized** — no hardcoded strategy windows. Every indicator takes explicit parameters.
2. **PIT-bounded** — all inputs filtered to `available_at <= as_of`. Outputs record `input_dataset_version` and `input_snapshot_id`.
3. **Neutral** — no buy/sell/bullish/bearish/rank/score/signal outputs. Only mechanically derivable values.
4. **Derived** — outputs are not canonical facts. They are rebuildable views or cache entries.
5. **Cacheable** — an optional `technical_indicator_cache` table may store frequently-used results. Cache entries are not canonical truth, must be reproducible, and are invalidated on input changes.

The indicator library is exposed via `lake.indicators.*` and returns `IndicatorResult` objects with metadata (parameters, code version, input snapshot).

A materialized cache is permitted but follows strict rules:

- Cache entries record input dataset version, snapshot ID, parameters hash, and code version.
- Cache entries are invalidated on: new bar ingestion, corporate action changes, security master changes, code version bumps, or parameter definition changes.
- Cache misses compute on demand or fail explicitly depending on caller policy.
- Cache reads preserve the same PIT guarantees as uncached reads.

**Consequences:**

- Positive: Consumers no longer reimplement common indicators; they compose from a shared, tested library.
- Positive: PIT-boundary enforcement is centralized and consistent, reducing subtle as-of bugs across consumers.
- Positive: The optional cache prevents redundant computation across strategies sharing the same indicator configuration.
- Positive: The neutral/strategy boundary is explicit and auditable — Alpha-Lake provides measurements, Alpha-Quant decides what they mean.
- Negative: Maintaining 60+ indicators requires ongoing test coverage and documentation.
- Negative: The cache adds storage and invalidation logic complexity.
- Negative: The cache must be explicitly designed so it cannot be mistaken for canonical truth — documentation, naming, and access patterns must reinforce this.

**References:**

- DESIGN.md §14
- ADR-0009: Fact store + transform library, never a feature store (refined by this ADR)
- Core indicator issue: #82

**Date:** 2026-06-19