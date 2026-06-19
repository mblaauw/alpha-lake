# ADR-0018: Derived news & social analytics layer (neutral, PIT-bounded, versioned)

**Status:** Accepted

**Context:**

The lake ingests news articles and social posts as canonical text datasets alongside
market data. These text datasets carry inherently subjective content — headlines,
commentary, opinion, rumor — and any derived metric (sentiment, topic, attention) is
a model-dependent annotation, not a market fact.

ADR-0009 established the principle that the lake computes neutral transforms and never
stores strategy features. ADR-0017 extended this to bar-derived technical indicators.
We now need the same discipline for text-derived analytics: measure attention and
sentiment neutrally, never decide what they mean.

Key challenges:

- Sentiment, topic labels, entity extraction, and embeddings are model-dependent and
  version-sensitive — they must never be mistaken for ground truth.
- Text analytics outputs can be cached for performance, but the cache must remain
  rebuildable from canonical text data.
- The boundary between "measurement" and "interpretation" must be explicit and
  auditable for news/social data, which is inherently more subjective than OHLCV bars.

**Decision:**

Alpha-Lake provides a neutral text-derived analytics layer that follows the same
principles as the technical indicator library (ADR-0017):

1. **Source-grounded canonical datasets** — `news_articles` and `social_posts`
   store raw text facts with full lineage and PIT metadata.
2. **Versioned derived datasets** — `entity_mentions`, `sentiment_annotations`,
   and `attention_metrics` store reproducible annotation/metric outputs with full
   lineage and PIT metadata; they are not source-grounded canonical truth.
3. **Neutral derived metrics** — volume, velocity, sentiment distribution, entity
   linkage, topic/event clustering, novelty, engagement, source quality, co-mentions,
   text features. All use labels that describe, not judge.
4. **Versioned annotations** — every derived text annotation records `model_version`,
   `prompt_version`, `taxonomy_version`, `input_text_hash`, `source_dataset_version`.
5. **PIT-bounded** — all derived values satisfy `available_at <= as_of`.
6. **Rebuildable cache** — an optional cache stores frequently-used NLP outputs
   and aggregated metrics, following the same rules as the indicator cache (§14.4).
7. **Forbidden outputs** — `bullish_news_signal`, `reddit_hype_score`,
   `buy_pressure_score`, `trade_candidate_rank`, `negative_catalyst_action`, and any
   output that interprets sentiment or attention as trading/risk signals.

**Consequences:**

- Positive: Consumers get a shared library of neutral text-derived metrics without
  reimplementing NLP pipelines.
- Positive: Version tracking on every annotation prevents silent model-upgrade drift.
- Positive: The neutral/strategy boundary is explicit and auditable for text data,
  which is more subjective than market data.
- Negative: Maintaining multiple NLP models, prompt versions, and taxonomies adds
  operational complexity.
- Negative: The subjective nature of text data requires careful documentation so
  consumers understand what each annotation means and does not mean.
- Negative: Entity extraction quality varies by source and domain; confidence scores
  must be surfaced transparently.

**References:**

- DESIGN.md §15
- ADR-0009: Fact store + transform library, never a feature store
- ADR-0017: Derived technical indicator library (neutral, PIT-bounded, cacheable)

**Date:** 2026-06-19
