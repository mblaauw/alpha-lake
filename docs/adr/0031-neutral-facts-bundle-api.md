# ADR-0031: Neutral Facts Bundle API

**Date:** 2026-06-26
**Status:** Accepted

## Context

Alpha-Quant (a downstream consumer) needs aggregated neutral market facts across
multiple symbols in a single response. Data needed includes price summaries,
readouts, fundamentals, insider transactions, earnings events, and attention
metrics — all PIT-bounded at a single `as_of` instant.

Previously, each data category required a separate API call, and readouts were
only available through the dashboard (unauthenticated) endpoint.

## Decision

Add a neutral Facts Bundle API alongside authenticated readout endpoints.

### New endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/v1/symbol/{symbol}/readouts` | Authenticated single-symbol readouts |
| POST | `/v1/readouts/batch` | Batch readouts |
| GET | `/v1/symbol/{symbol}/facts-bundle` | Aggregated neutral facts |
| POST | `/v1/facts-bundle/batch` | Batch facts bundle |

### Readout service extraction

The readout computation logic was extracted from `transport/dashboard.py` into
a shared `serving/readouts.py` module. The dashboard endpoint is now a thin
wrapper around the same service, ensuring dashboard and authenticated paths
produce identical results.

### Decision-panel enhancement

The existing `/v1/decision-panel` endpoint (used by Alpha-Quant) gained:
- `include` parameter for optional sections (readouts, insider_transactions_detail)
- `capabilities` list in response advertising available extras

The decision-panel remains internally composed from shared facts-bundle helpers.

### Facts bundle sections

- `price` — latest bar summary
- `readouts` — neutral measurements (from shared service)
- `fundamentals` — PIT fundamental metrics
- `insider_tx` — aggregated insider sentiment (existing surface)
- `earnings_events` — earnings calendar events
- `attention_metrics` — experimental, flagged in `experimental_sections`

### No-strategy boundary

- No opinion fields (buy/sell, ranking, recommendation)
- All sections are PIT-bounded by `available_at <= as_of`
- `snapshot_id` is threaded through all sub-reads for reproducibility
- Missing sections are reported in `missing_sections`, not fabricated
- Experimental sections are flagged explicitly

## Consequences

### Positive

- Single API call replaces 4+ calls for Alpha-Quant
- Consistent readout computation across dashboard and authenticated paths
- Batch endpoints reduce latency for multi-symbol consumers
- Clear audit trail for missing/experimental data

### Negative

- More transport surface area to maintain
- Facts bundle response is large for symbols with all data sections
- Shared service extraction increased coupling between dashboard and serving

### Mitigations

- All new endpoints require API key auth
- Research paths require explicit `as_of`; `latest=true` is explicit non-research
- Dashboard endpoints remain unchanged (backward-compatible)
- READOUTS registry and shared service ensure consistency
