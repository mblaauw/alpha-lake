# ADR-0004: Deterministic replay via content-addressed raw archive

**Status:** Accepted

**Context:**
Bug fixes in parsing or validation should not require re-fetching data from upstream sources. The pipeline must be fully reproducible from stored raw data.

**Decision:**
Archive every raw API payload verbatim to content-addressed Zstd-compressed blobs before any parsing. The archive path includes source, dataset, and date. `content_hash` is SHA-256 of raw bytes for archive integrity and storage deduplication. Canonical version identity uses `version_hash`, a SHA-256 of canonicalized records under the pinned parser/normalization recipe. Replay reads raw archive → parse → validate → canonicalize, producing the same output for the same parser/schema/config/calendar versions.

**Consequences:**
- Positive: Full reproducibility without upstream dependencies
- Positive: Debugging by replaying raw payloads through new parser versions
- Positive: Raw deduplication via content addressing and semantic deduplication via `version_hash`
- Negative: Storage cost for raw payloads (mitigated by Zstd compression)

**References:**
- DESIGN.md §8, §9, §21

**Date:** 2026-06-18
