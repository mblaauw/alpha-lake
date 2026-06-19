---
name: dataset-contract
description: Alpha-Lake dataset contract YAML template and validation gate. Use when adding or changing contracts, schema versions, dataset APIs, or CI contract checks.
---

# Dataset Contract

Contracts are the dataset API. Table layout is implementation detail.

## File Pattern

```text
contracts/<dataset>.vN.yaml
```

## Required Sections

```yaml
dataset: bars
version: 1
primary_key:
  - security_id
  - effective_date
  - source_id
partition_key:
  - effective_date
pit_columns:
  valid_time: effective_date
  knowledge_time: available_at
required_fields:
  - security_id
  - effective_date
  - available_at
  - source_id
  - content_hash
  - version_hash
nullable_fields:
  - source_published_at
freshness_sla:
  calendar: exchange
  rule: available_by_next_trading_day
quality_status:
  allowed: [valid, quarantined, stale]
compatibility:
  additive_nullable: compatible
  required_field_change: major
```

## Checklist

- Include temporal columns.
- Include lineage columns.
- Define freshness SLA and calendar basis.
- Define allowed quality statuses.
- Define backward-compatibility rules.
- Version major on required-field, PK, semantic, or type-breaking changes.

## Gates

```bash
rg -n "version_hash|available_at|effective_date|quality_status" contracts
just lint
```

## Forbidden

- Do not treat contracts as generated table docs only.
- Do not change required fields without version bump.
- Do not omit PIT columns.
- Do not encode strategy outputs in contracts.
