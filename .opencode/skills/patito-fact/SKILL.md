---
name: patito-fact
description: Alpha-Lake Patito fact model template and validation gates. Use when defining fact schemas, Polars normalization outputs, Patito checks, or dataset validation.
---

# Patito Fact

Fact model = schema = validator. Use Patito after Polars normalize and before canonical write.

## Mandatory Fields

```text
effective_date, available_at, source_published_at, ingested_at, validated_at
security_id, source_id, schema_version, parser_version
source_fetch_id, raw_payload_hash, ingestion_run_id
content_hash, version_hash, quality_status
```

## BarFact Example

```python
import patito as pt
import polars as pl


class BarFact(pt.Model):
    security_id: str
    effective_date: pl.Date
    available_at: pl.Datetime
    source_id: str
    open: float = pt.Field(ge=0)
    high: float = pt.Field(ge=0)
    low: float = pt.Field(ge=0)
    close: float = pt.Field(ge=0)
    volume: int = pt.Field(ge=0)
    content_hash: str
    version_hash: str
```

Add custom checks for:

```text
low <= open <= high
low <= close <= high
large return requires known corp-action context
effective_date is exchange-session date
available_at is UTC
```

## Version Hash Recipe

`version_hash = sha256(canonicalized_records)` using sorted keys, normalized numeric precision, normalized dates, stable nulls, deterministic row ordering, and `normalization_version`.

## Gates

Run the full invariant gate in `alpha-lake-invariants` before committing.

## Forbidden

- Do not use `content_hash` as semantic version identity.
- Do not mint `security_id` in Patito models.
- Do not add strategy labels or scores to facts.
- Do not accept negative price/volume or impossible OHLC.
