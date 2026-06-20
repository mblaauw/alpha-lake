---
name: add-dataset
description: Alpha-Lake dataset vertical-slice template. Use when adding bars, fundamentals, insider, corporate actions, news, social, earnings, or any new dataset.
---

# Add Dataset

Use this as the orchestrator. Pull details from `connector`, `patito-fact`, `pit-reader`, `golden-replay`, and `dataset-contract`.

## Fill-In Plan

| Step | Output |
|---|---|
| Dataset descriptor | `Dataset(table, Model, keys)` entry in `DATASETS` registry — DDL, key map, and `write()` derive automatically |
| Connector | httpx+tenacity resource that archives before parse, registered via `get_connector()` |
| Raw archive | Manifest row with `content_hash`, fetch metadata, parser intended |
| Normalize | Polars transform to typed canonical-shape frame |
| Validate | Patito fact model gate |
| Version | Compute semantic `version_hash` |
| Write | `write(con, "dataset_name", df)` — single function handles all datasets |
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
1. Register Dataset descriptor: add Dataset(table=<table>, model=<FactClass>,
   natural_keys=(...)) to DATASETS in src/alpha_lake/canonical/__init__.py.
2. Add source_registry + source_dataset_registry seed rows.
3. Implement connector that emits raw fetch metadata only (see connector skill).
4. Archive raw bytes and manifest before parsing.
5. Normalize with Polars into <Dataset>Fact columns.
6. Validate with Patito <Dataset>Fact.
7. Compute version_hash from canonicalized records.
8. Write via write(con, <table>, df) — DDL and merge derive from descriptor.
9. Add PIT reader and leakage test.
10. Add contract and replay fixture.
```

## Gates

Run the full invariant gate in `alpha-lake-invariants` before committing.

## Forbidden

- Do not skip raw archive.
- Do not write canonical rows from connector code.
- Do not use `content_hash` as canonical version identity.
- Do not add latest-by-default readers.
- Do not omit contract or replay coverage.
- Do not hand-wire MERGE or DDL — the `DATASETS` descriptor handles it.
