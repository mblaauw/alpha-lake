# Refinement Gate: Epic #424 → (next epic)

**Status:** Assessment complete — epic closing
**Last assessed:** 2026-06-24

## Child Issue Audit

| # | Title | PR | Status |
|---|-------|----|--------|
| 425 | Fix price_mode toggle in /bars/summary + /bars endpoints | #430 | Merged |
| 426 | Add /macro/{series_id} dashboard endpoint | #431 | Merged |
| 427 | Add /insider/{symbol} dashboard endpoint | #432 | Merged |
| 428 | Add /analyst/{symbol} dashboard endpoint | #433 | Merged |
| 429 | Docs & ADRs correctness sweep | #434 | Merged |

All 5 sub-issues completed and merged.

## Gate Checklist

### Functional completeness

- [x] price_mode dropdown (raw/split) changes bar data in both `/bars` and `/bars/summary`
- [x] `total_return` price mode removed from UI (kernel only implements split adjustment)
- [x] `/macro/{series_id}` returns PIT-bounded FRED series observations
- [x] `/insider/{symbol}` returns insider transactions for a ticker
- [x] `/analyst/{symbol}` returns analyst estimate consensus
- [x] `security_detail` datasets param default fixed (`None` → `""`)
- [x] All endpoints validate price_mode against `_VALID_PRICE_MODES`

### Documentation

- [x] `docs/serving-api.md` updated with all new endpoint paths
- [x] `docs/DESIGN.md` updated for endpoint gaps
- [x] ADRs reviewed for correctness
- [x] Missing endpoints added to serving-api docs

### Endpoint & GUI deep sweep

- [x] Dead code removed: `_REVERSE_INDICATOR_MAP`, `_symbol_for()`, `_INDICATOR_DASH_MAP`
- [x] `technical_indicators` SQL query wrapped in try/except (was 500-crashing before fallback)
- [x] `attention_metrics` + `sentiment_annotations` query blocks separated
- [x] `window.__leaders` global replaced with module-scoped `_leaders`
- [x] 4 dead CSS groups removed
- [x] `donchian_middle` glossary entry moved from Volume → Volatility category
- [x] App.js timezone bug fixed (`as_of` datetime-local uses local time, not UTC)
- [x] `_indicatorResults` cache added to `renderIndicators()` for instant category switches
- [x] `return_126`/`return_252` added to `IND_DEFS_EXTRA`
- [x] Stale `NEW:` comment removed in styles.css

### Non-UI code deep sweep

- [x] Forbidden tokens renamed: `bullish`/`bearish` → `aligned_up`/`aligned_down` in `ma_stack`; `bullish_div`/`bearish_div` → `positive_div`/`negative_div` in `rsi_divergence`
- [x] Dead code removed: `_SPY_SECURITY_ID` constant, `_prev_month_start()`, `_model_cols`
- [x] Inner `_v`/`_b` functions moved out of loop in `compute_all_indicators` (redefined per iteration)
- [x] `as_of` PIT filter added to `compute.py`, `relative_strength.py`, `market_breadth.py`, `vol_term_structure.py`
- [x] Length mismatch guard and benchmark pre-computation in `relative_strength.py`
- [x] Docstring/code mismatch fixed in `event_aggregations.py` (`rank_change` → `rank`)
- [x] Dead `if total > 0 else None` removed in `event_aggregations.py`
- [x] Stale `_SPY_SECURITY_ID` import removed from `flows/__init__.py`

### Test coverage

- [x] `just test` passes: 243/245 (2 pre-existing infra DNS/storage failures)
- [x] `just lint` clean (ruff + ty + import-linter)
- [x] Forbidden-token grep clean
- [x] All indicator tests green (`test_indicators.py`, `test_technical_indicators.py`)

### Development notes

- `total_return` removed from price mode because kernel only implements split-adjusted prices, not dividend adjustments
- Two endpoint + GUI deep sweeps performed (7 files then 6 files)
- Non-UI code deep sweep covered 30+ files across core library, connectors, normalize, derived, models, kernel SQL
