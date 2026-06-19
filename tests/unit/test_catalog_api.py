from datetime import date, datetime, timezone

import duckdb
import polars as pl

from alpha_lake.canonical import write_bars
from alpha_lake.catalog import dataset_health, list_datasets


def test_list_datasets():
    con = duckdb.connect()
    from pathlib import Path
    schema = Path("src/alpha_lake/catalog/schema.sql").read_text()
    for stmt in schema.split(";"):
        s = stmt.strip()
        if s:
            con.execute(s)

    datasets = list_datasets(con)
    names = [d["dataset"] for d in datasets]
    assert "lake_bars" in names
    assert "source" in names


def test_dataset_health():
    con = duckdb.connect()
    ts = datetime(2026, 1, 5, 16, 0, tzinfo=timezone.utc)
    df = pl.DataFrame({
        "security_id": ["sec_t"], "effective_date": [date(2026, 1, 5)],
        "available_at": [ts], "source_id": ["eodhd"],
        "open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5],
        "volume": [10000], "source_fetch_id": [""], "raw_payload_hash": [""],
        "ingestion_run_id": [""], "content_hash": [""], "version_hash": [""],
        "schema_version": [1], "parser_version": [1], "quality_status": ["valid"],
        "source_published_at": [None], "ingested_at": [None], "validated_at": [None],
    }).with_columns(
        pl.col("source_published_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("ingested_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("validated_at").cast(pl.Datetime(time_zone="UTC")),
    )
    write_bars(con, df)

    h = dataset_health(con, "lake_bars")
    assert h["status"] == "ok"
    assert h["rows"] == 1
