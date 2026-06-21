# ADR-0025: Dataset support tiers and experimental text sources

**Status:** Accepted

**Context:**
Alpha-Lake currently has schemas and connectors for market facts, text facts, and text-derived
analytics. The reliable product value is PIT-correct fact data: bars, corporate actions,
fundamentals, events, insider transactions, and security identity. The current text sources
are thin, unreliable, licensing-sensitive, and not authoritative. The text-derived analytics
schemas exist, but there is no supported implementation that turns them into product value.

At the same time, broad technical indicator coverage is commodity convenience. Customers can
compute many indicators from bars themselves. Alpha-Lake's moat is not indicator breadth; it
is PIT-correct, reconciled, corporate-action-aware facts.

**Decision:**
Represent dataset product posture as registry/config data and classify datasets into three
tiers:

- **Core:** sellable, SLA-eligible, reproducible, and reconciliation candidates. This covers
  bars, read-time adjusted bars, corporate actions, fundamentals, earnings, insider
  transactions, and security master.
- **Convenience:** supported helpers over core facts. Technical indicators live here; the
  priority is correctness and warm-up/lookback behavior, not breadth.
- **Experimental:** retained for optionality, not supported, no SLA, disabled by default. This
  covers news, social, entity mentions, sentiment annotations, and attention metrics.

Do not delete text schemas or connector code. Keep them dormant and opt-in only until there is
a licensed, reliable source or a paying customer requirement. Default stack config disables
experimental text connectors.

**Consequences:**
- Positive: Supported product surface aligns with Alpha-Lake's fact-layer moat.
- Positive: News/social maintenance and licensing risk are reduced without losing optionality.
- Positive: Source enablement and product posture remain data, not ad hoc serving behavior.
- Positive: Investment direction is clear: PIT fundamentals, corporate actions, multi-source
  reconciliation, intraday bars, delisted universe support, and history depth.
- Negative: Customers who want text data must explicitly opt in and accept experimental/no-SLA
  posture.
- Negative: Existing text schemas remain in the registry, so docs and UI surfaces must avoid
  presenting them as supported outputs.

**References:**
- ADR-0006: Read-time adjusted price computation
- ADR-0014: Source registry as data; precedence/freshness not hardcoded
- ADR-0017: Derived technical indicator library
- ADR-0018: Derived news & social analytics layer
- docs/product-tiers.md
- Related issue: #368

**Date:** 2026-06-21
