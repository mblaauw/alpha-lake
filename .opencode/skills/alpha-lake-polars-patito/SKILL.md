# alpha-lake-polars-patito

Polars + Patito patterns for the Alpha-Lake data pipeline. Per ADR-0019, the fact model *is* the schema *is* the validator.

## Pipeline boundary

```
dlt fetch → raw archive → Polars parse → Patito validate → DuckLake bitemporal write → DuckDB serve
```

- **Polars** for parse/normalize: raw JSON/CSV → typed columns, renaming, coercion, date parsing, deduplication, row-wise transforms.
- **Patito** for gate validation after normalize, before canonical write.
- **DuckDB SQL** for set-oriented transforms (joins, aggregations, window functions) and serving queries.

## Cardinal rule

**Never both Polars and DuckDB for the same transform job.** Arrow zero-copy between them means there is no serialisation cost to switching, but mixing paradigms in one pipeline step hurts readability and maintainability. A single step uses either Polars expressions or DuckDB SQL — not both.

## Fact model pattern

Define a fact model as a `patito.DataFrameModel` that doubles as a Pydantic model:

```python
import patito as pt
import polars as pl
from typing import ClassVar


class BarFact(pt.DataFrameModel):
    security_id: str = pt.Field(unique=True)
    ts_event: pl.Datetime = pt.Field(dtype=pl.Datetime)
    price: float = pt.Field(
        constraints=[pt.Check(lambda x: x > 0, "price_positive")]
    )
    volume: int = pt.Field(constraints=[pt.Check(lambda x: x >= 0, "volume_non_negative")])
    _nullable: ClassVar[set[str]] = set()
```

Use in a pipeline step:

```python
fact = BarFact.validate(
    df,
    skip_checks=False,  # fail fast on gate
)
```

Patito validates per-column constraints, uniqueness, nullability, and dtypes in a single call. Descriptive errors include per-column summaries.

## Arrow zero-copy

Polars DataFrames, Patito validated frames, and DuckDB relations all share the Arrow columnar format. No serialisation or copies are needed when moving between them:

```python
import polars as pl
import duckdb

lf: pl.LazyFrame = pl.scan_parquet("raw/*.parquet")
rel = duckdb.from_arrow(lf.collect().to_arrow())  # zero-copy
```

## References

- ADR-0019: Polars + Patito for DataFrame processing and model validation
- DESIGN.md §23 (tech stack), §28.Phase 1 (bars vertical slice), §29 (tech stack table)
