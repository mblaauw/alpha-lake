---
name: alpha-lake-invariants
description: Alpha-Lake invariants, forbidden tokens, PIT/leakage guardrails, and pre-commit gates. Use before changing canonical data, readers, replay, derived outputs, or dataset code.
---

# Alpha-Lake Invariants

Use this first for any change touching `src/alpha_lake`, `docs/DESIGN.md`, ADRs, contracts, canonical data, readers, replay, or derived outputs.

## Pre-Flight Checklist

Answer yes before editing:

- Raw payloads/manifests/fixtures stay immutable except documented text-erasure tombstones.
- Canonical facts carry lineage and map to a DuckLake snapshot.
- No strategy/decision semantics enter Alpha-Lake.
- Corrections create new `available_at` versions; they never overwrite prior knowledge.
- Research reads require `as_of` and enforce `available_at <= as_of`.
- Historical observations exclude future `effective_date`; known-future events may expose future event dates only when already knowable.
- `security_id` is deterministic from stable IDs, never random or symbol-prefixed.
- `content_hash` is raw-byte archive integrity; `version_hash` is semantic canonical identity.
- All instants are UTC; `effective_date` is exchange-local session date from the pinned calendar.

## Runnable Gates

Run before commit:

```bash
rg -n "\b(signal|bullish|bearish|buy|sell|golden_cross)\b" src docs contracts
rg -n "\b(rank|score)\b" src/alpha_lake/canonical src/alpha_lake/models
rg -n "as_of\s*=\s*None|latest\s*=\s*True|def .*latest" src/alpha_lake
rg -n "datetime\.now\(|datetime\.utcnow\(|time\.time\(" src/alpha_lake/canonical src/alpha_lake/replay src/alpha_lake/flows
rg -n "uuid4\(|random\.|secrets\.token" src/alpha_lake/security_master src/alpha_lake/canonical
rg -n "AAPL-|MSFT-|symbol.*security_id|security_id.*symbol" src/alpha_lake docs
just lint
```

If a gate matches, stop and inspect. Only continue when the match is test data, docs explicitly explaining forbidden behavior, or an approved exception.

## Canonical Example

Good canonical row fields:

```text
security_id=sec_<deterministic_hash>
effective_date=exchange_session_date
available_at=UTC instant
content_hash=sha256(raw bytes)
version_hash=sha256(canonicalized records)
source_fetch_id, ingestion_run_id, schema_version, parser_version
```

## Forbidden

- Do not use strategy labels: `signal`, `bullish`, `bearish`, `buy`, `sell`, `golden_cross`.
- Do not put `rank` or `score` on canonical or derived paths unless it is a neutral measurement explicitly allowed by DESIGN.md.
- Do not default research reads to latest.
- Do not use wall-clock `now()` in canonical/replay decisions; use recorded manifest times.
- Do not mint random or symbol-prefixed `security_id` values.

## Workflow Rules

- Every issue requires a PR before closing. No issue moves to Done without an associated pull request.
- PRs must link to the issue they resolve (e.g. `Closes #N` in the description).
- Do not close issues directly; always close via merged PR.

## Stronger-Model Gate

Route to a stronger model or cross-check with invariants for PIT reader logic, deterministic `security_id`, semantic `version_hash`, and golden replay determinism.
