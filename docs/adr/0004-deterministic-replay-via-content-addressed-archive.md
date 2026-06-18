# ADR-0004: Deterministic replay via content-addressed raw archive

**Status:** Proposed

**Context:**
Bug fixes in parsing or validation should not require re-fetching data from upstream sources. The pipeline must be fully reproducible from stored raw data.

**Decision:**
Archive every raw API payload verbatim to content-addressed Zstd-compressed blobs before any parsing. The archive path includes source, dataset, and date. Content addressing is by SHA-256 of the raw payload. Replay reads raw archive → parse → validate → canonicalize, producing the same output for the same parser/schema/config versions.

**Consequences:**
- Positive: Full reproducibility without upstream dependencies
- Positive: Debugging by replaying raw payloads through new parser versions
- Positive: Deduplication via content addressing
- Negative: Storage cost for raw payloads (mitigated by Zstd compression)

**References:**
- DESIGN.md §5.1

**Date:** 2026-06-18
