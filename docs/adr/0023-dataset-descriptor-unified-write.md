# ADR-0023: Dataset descriptor for unified canonical write

**Status:** Accepted

**Context:**
The original canonical write path required per-dataset boilerplate: each dataset defined its own hand-wired MERGE SQL with hardcoded column lists, key expressions, and table names. Adding a new dataset meant copying an existing write function, modifying the MERGE SQL, managing a separate `ensure_schema` call, and tracking the key columns in a second location. This was error-prone and made the DATASETS registry underutilized — the registry held table and model metadata but no write logic could be derived from it.

After the architectural coherence refactor (Epic #308), two patterns converged:
1. Every canonical write follows the same MERGE-on-natural-keys-plus-available_at pattern with a version_hash dedup check.
2. The `Dataset` dataclass already captured `table`, `model` (Patito Model), and `natural_keys` — the three pieces needed to derive DDL, MERGE SQL, and the key join expression.

**Decision:**
Replace per-dataset hand-wired MERGE functions with a single generic `write(con, dataset, df)` function that derives DDL and MERGE SQL from the `Dataset` descriptor:

- A `@dataclass(frozen=True)` `Dataset` holds `table`, `model`, and `natural_keys`.
- A `DATASETS: dict[str, Dataset]` registry maps logical names to descriptors.
- `_generate_ddl(model, table)` introspects the Patito `Model`'s `model_fields` to produce `CREATE TABLE IF NOT EXISTS` DDL with DuckDB types derived from Python type annotations.
- `write(con, dataset, df)` calls `compute_version_hash`, `ensure_schema`, then a single generic `MERGE INTO` using `dataset.natural_keys + ["available_at", "version_hash"]` as the dedup key.
- Per-dataset convenience functions (`write_bars`, `write_corp_actions`, `write_dataset`) are thin wrappers over the generic `write()`.

The dedup key is always `natural_keys + (available_at, version_hash)` because:
- `natural_keys` define the business identity of a row (e.g., `security_id + effective_date + source_id` for bars).
- `available_at` creates a new version on each knowledge-time update.
- `version_hash` prevents re-inserting an identical payload that was already seen at the same `available_at`.

**Consequences:**
- *Positive:* Adding a dataset requires only a `Dataset(...)` entry in `DATASETS` — no new MERGE SQL, no new DDL logic, no new key-tracking code.
- *Positive:* `_generate_ddl` maps Python types (`str → VARCHAR`, `int → BIGINT`, `float → DOUBLE`, `datetime → TIMESTAMPTZ`, `date → DATE`) automatically, keeping the Patito model as the single schema source of truth.
- *Positive:* The `ensure_schema → MERGE → count` pipeline is identical across all datasets, enabling consistent auditing and profiling.
- *Positive:* The `Dataset` descriptor is serializable and can be re-read from a catalog or config source in the future without changing the write path.
- *Negative:* `_generate_ddl` handles only the core type set; custom DuckDB types (e.g., `LIST`, `STRUCT`, `DECIMAL`) require explicit annotation handling in `_type_to_duckdb`.
- *Negative:* `normalization_version` is injected as an audit column but is not part of the dedup key — a normalization version bump produces a new `version_hash` naturally via `compute_version_hash`, so no special version-column logic is needed in the MERGE.

**Implementation:**
- `src/alpha_lake/canonical/__init__.py`: `Dataset` dataclass, `DATASETS` registry, `_generate_ddl`, `write`, `compute_version_hash`, `ensure_schema`.
- MERGE uses `WHEN NOT MATCHED THEN INSERT` only — updates are never applied to canonical rows (raw is immutable; corrections are new `available_at` versions per invariant I4).
