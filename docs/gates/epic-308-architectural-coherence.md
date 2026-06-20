# Refinement Gate: Epic 308 — Architectural Coherence

**Status:** Assessment complete — epic closing
**Last assessed:** 2026-06-20

## Child Issue Audit

| # | Title | PR | Status |
|---|-------|----|--------|
| 309 | A — Dataset Descriptor | #316 | Merged |
| 310 | C — Clock in Write Path | #317 | Merged |
| 311 | B — Wire Connector Layer | #318 | Merged |
| 312 | D — PIT Builder | #319 | Merged |
| 313 | E — Vectorise | #320 | Merged |
| 315 | F — Cleanup | #321 | Merged |
| 314 | REF — Refinement Gate | — | This PR |

## Invariant Compliance

- [x] No strategy semantics anywhere (forbidden-token grep clean)
- [x] All `as_of` reads require explicit parameter (no silent `latest`)
- [x] Raw data immutable; corrections flow as new `available_at` versions
- [x] Wall-clock eliminated from canonical and replay paths (Clock ABC)
- [x] `compute_version_hash` is a pure function of stable inputs (sorted keys, UTC timestamps, pinned float repr, fixed normalization_version)
- [x] Adjusted prices are read-time and PIT-bounded; never stored
- [x] Dates use trading calendar; instants are UTC

## Metrics

- **105 total tests** (104 pass, 1 skipped)
- **Golden replay**: passes (fixtures re-frozen 3× during epic)
- **`just lint`**: 92 pre-existing errors remain (E501 line-length)
- **import-linter**: clean
- **Forbidden-token grep**: clean (only MACD `signal_line` — standard financial term)

## Cleanup Summary

- Removed 4 dead files (225 lines): `derived/serving.py`, `derived/text_serving.py`, `derived/annotations.py`, `ports/__init__.py`
- Removed dead functions: `catalog.resolve_ingestion_run`, `calendar_.CALENDAR_VERSION`
- Removed unused type aliases: `models.SecurityId`, `models.SourceId`
- Removed unused imports: `httpx` (cli.py), `timezone` (flows), `backfill_bars` (dagster_assets)

## Sign-off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Developer | | | |

## Outcome

- [x] **Pass** — Epic 308 complete. All child issues closed via merged PRs.
