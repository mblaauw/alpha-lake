# Product Dataset Tiers

Alpha-Lake ships facts first. Supported product value comes from point-in-time-correct,
reconciled, corporate-action-aware market facts that customers cannot easily rebuild from
commodity vendor exports.

## Tier 1: Core

Core datasets are sellable, SLA-eligible, reproducible, and candidates for reconciliation.

- `lake_bars`
- Read-time adjusted bars
- `corp_actions`
- `fundamentals`
- `earnings_calendar`
- `insider_tx`
- `security_master`

Core investment priority is fact-layer correctness: PIT fundamentals, corporate-action
coverage, multi-source reconciliation for fundamentals and corporate actions, intraday
bars, delisted securities, and deeper history.

## Tier 2: Convenience

Convenience outputs are supported helpers over core facts, but they are not the moat.

- Technical indicators

The indicator library should stay small and correct. The priority is PIT-bounded reads,
deterministic warm-up/lookback behavior, and stable neutral measurements, not indicator
breadth.

## Tier 3: Experimental

Experimental datasets are retained for optionality but are not supported product outputs,
not SLA-eligible, and disabled by default.

- `news_articles`
- `social_posts`
- `entity_mentions`
- `sentiment_annotations`
- `attention_metrics`

Text sources remain dormant because the current free sources are unreliable,
licensing-sensitive, and not authoritative. The schemas and connector code stay in the
repository so a licensed, reliable source can be enabled by explicit config opt-in without
rebuilding the bitemporal archive model.

## Default Posture

`config/stack.toml` is the source of truth for product tier metadata and default source
enablement. Experimental text connectors are disabled by default. Opt-in requires changing
the relevant `source_datasets.*.*.enabled` setting in config.
