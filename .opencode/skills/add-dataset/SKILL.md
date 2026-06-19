---
name: add-dataset
description: Alpha-Lake dataset vertical-slice template. Use when adding bars, fundamentals, insider, corporate actions, news, social, earnings, or any new dataset.
---

# Add Dataset

Use this as the orchestrator. Pull details from `connector`, `patito-fact`, `pit-reader`, `golden-replay`, and `dataset-contract`.

## Fill-In Plan

| Step | Output |
|---|---|
| Registry | `source_registry` + `source_dataset_registry` seed rows |
| Connector | dlt/httpx resource that archives before parse |
| Raw archive | Manifest row with `content_hash`, fetch metadata, parser intended |
| Normalize | Polars transform to typed canonical-shape frame |
| Validate | Patito fact model gate |
| Version | Compute semantic `version_hash` |
| Write | DuckDB MERGE into DuckLake on `available_at` knowledge time |
| Read | PIT reader with required `as_of` |
| Contract | `contracts/<dataset>.vN.yaml` |
| Tests | connector fixture, validation, PIT leak, replay, property checks |

## Mandatory Columns

Every canonical dataset carries:

```text
effective_date
available_at
source_published_at
ingested_at
validated_at
security_id
source_id
schema_version
parser_version
source_fetch_id
raw_payload_hash
ingestion_run_id
content_hash
version_hash
quality_status
```

## Worked Skeleton

```text
1. Add registry rows for <dataset>/<source>.
2. Implement connector that emits raw fetch metadata only.
3. Archive raw bytes and manifest before parsing.
4. Normalize with Polars into <Dataset>Fact columns.
5. Validate with Patito <Dataset>Fact.
6. Compute version_hash from canonicalized records.
7. MERGE via DuckDB into DuckLake with available_at versioning.
8. Add PIT reader and leakage test.
9. Add contract and replay fixture.
```

## Gates

```bash
rg -n "datetime\.now\(|uuid4\(|signal|bullish|bearish|buy|sell" src/alpha_lake
just lint
```

## Forbidden

- Do not skip raw archive.
- Do not write canonical rows from connector code.
- Do not use `content_hash` as canonical version identity.
- Do not add latest-by-default readers.
- Do not omit contract or replay coverage.
