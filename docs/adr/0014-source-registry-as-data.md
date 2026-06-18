# ADR-0014: Source registry as data; precedence/freshness not hardcoded

**Status:** Proposed

**Context:** Source behavior (precedence, freshness SLA, retry policy, parser version) must be configurable without code changes.

**Decision:** All source behavior is data, not code. One row per source in a registry table drives connectors, precedence, freshness, and reconciliation.

**Consequences:**
- Positive: New sources added without code changes
- Positive: Precedence reordering without deployment
- Negative: Registry must be seeded and maintained

**References:**
- DESIGN.md §7

**Date:** 2026-06-18
