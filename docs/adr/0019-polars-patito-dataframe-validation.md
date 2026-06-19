# ADR-0019: Polars + Patito for DataFrame processing and model validation

**Status:** Proposed

**Context:**
Alpha-Lake ingests, normalizes, and validates raw market data before writing it as canonical bitemporal facts. Two critical pipeline stages—parsing raw records into structured rows and validating those rows against a contract—need a DataFrame library and a schema/validation approach.

DuckDB SQL alone is suboptimal for the normalize stage because raw data often requires row-wise transformations, columnar expression chaining, and streaming from HTTP sources before it is shaped into relational form. A purpose-built DataFrame library handles these patterns more ergonomically than composing SQL strings.

The project already uses Pydantic for configuration models. A validation layer that reuses Pydantic knowledge rather than introducing a second schema language reduces cognitive overhead and keeps the fact model definition as the single source of truth.

**Decision:**
Use Polars as the DataFrame library and Patito as the validation layer:

- **Polars** for all parse/normalize steps: raw JSON/CSV → typed columns, column renaming, type coercion, date/time parsing, deduplication, and row-wise transformations.
- **Patito** (`patito.DataFrameModel`) for gate validation after normalize, before canonical write: the fact model definition *is* the schema *is* the validator.
- DuckDB SQL remains the engine for set-oriented transforms (joins, aggregations, window functions) and for all serving queries — a single data-processing job uses either Polars or DuckDB, never both.

The pipeline boundary is:
```
dlt fetch → raw archive → Polars parse → Patito validate → DuckLake bitemporal write → DuckDB serve
```

Patito models inherit from Pydantic `BaseModel`, so existing Pydantic patterns (field types, validators, `model_config`) apply directly. A `BarFact` dataframe model carries both the column schema and per-row validation logic in one class.

**Consequences:**
- Positive: Arrow-native zero-copy between Polars, Patito, and DuckDB; no serialization overhead.
- Positive: Fact model = Pydantic model = Patito `DataFrameModel`; no redundant schema definitions.
- Positive: Polars lazy evaluation (`pl.LazyFrame`) enables query optimisation in the normalize pipeline without eagerly materialising.
- Positive: Patito provides descriptive validation errors with per-column summaries, aiding debugging and observability.
- Negative: Patito has a small community and slower release cadence than Polars; may lag on Polars or Pydantic upgrades.
- Negative: Two data-processing paradigms (Polars expressions, DuckDB SQL) in the same project; requires discipline to enforce the "never both for the same job" rule.
- Negative: Streaming ingestion sources that produce Arrow natively (some dlt sources) can bypass Polars entirely, making Patito validation an extra pass.

**References:**
- DESIGN.md §23 (tech stack), §27 (ADR table), §28 (build plan, Phase 1), §29 (tech stack table)
- Related issues: #NNN

**Date:** 2026-06-19
