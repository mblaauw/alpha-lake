---
name: golden-replay
description: Alpha-Lake deterministic replay, freeze-fixtures, and Hypothesis temporal property tests. Use when changing replay, fixtures, canonical writes, parser versions, or temporal tests.
---

# Golden Replay

Replay proves deterministic business output and deterministic bitemporal visibility.

## Replay Checklist

- Freeze raw payloads and manifests.
- Freeze canonical rows and `available_at` values.
- Freeze security-master snapshot and corporate actions.
- Freeze parser/schema/calendar versions.
- Freeze `content_hash` and `version_hash`.
- Compare business output and visible rows for each `as_of`.

## Determinism Inputs

```text
sorted JSON keys
stable null representation
pinned float/decimal precision
UTC instants
exchange-calendar version
deterministic security_id
normalization_version
parser_version
schema_version
```

## Hypothesis Properties

Generate histories with random ingest order, backfills, and restatements. Assert:

```text
no read returns available_at > as_of
knowledge-time reads are monotonic
restatements never mutate prior visible versions
replay output hash is stable for same inputs
```

## Commands

```bash
just replay
uv run pytest tests/replay/ tests/boundary/
```

## Golden Hash Scope

Hash both:

```text
business output rows
visibility set: primary key + available_at + version_hash + source_id
```

## Forbidden

- Do not use wall-clock time during replay.
- Do not generate random IDs.
- Do not hash unordered dicts or source envelopes as semantic identity.
- Do not compare only business values and ignore row visibility.

## Stronger-Model Gate

Use stronger model or cross-check with `alpha-lake-invariants` skill for replay determinism, `security_id`, `version_hash`, and Hypothesis temporal properties.
