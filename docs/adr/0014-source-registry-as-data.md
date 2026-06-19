# ADR-0014: Source registry as data; precedence/freshness not hardcoded

**Status:** Proposed

**Context:** Source behavior (retry policy, rate limits, precedence, freshness SLA, parser version) must be configurable without code changes. Precedence and freshness are dataset-specific: a supplier can be primary for one dataset and secondary or validation-only for another.

**Decision:** All source behavior is data, not code. Use `source_registry` for source-level connector mechanics and `source_dataset_registry` for dataset-specific role, priority, cadence, freshness SLA, parser version, contract version, and enablement.

**Consequences:**
- Positive: New sources added without code changes
- Positive: Precedence reordering without deployment
- Positive: One source can have different authority, freshness, and parser settings per dataset
- Negative: Registry must be seeded and maintained

**References:**
- DESIGN.md §7

**Date:** 2026-06-18
