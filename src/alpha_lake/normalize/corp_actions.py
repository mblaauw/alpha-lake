from __future__ import annotations

from datetime import datetime
from typing import Any

import polars as pl

_SOURCE_MAP: dict[str, str] = {
    "eodhd_splits": "eodhd",
    "tiingo_splits": "tiingo",
    "eodhd_dividends": "eodhd",
    "tiingo_dividends": "tiingo",
}


def splits_from_json(
    raw: list[dict[str, Any]],
    security_id: str,
    source_key: str,
    source_fetch_id: str,
    ingestion_run_id: str,
    content_hash: str,
    available_at: datetime,
) -> pl.DataFrame:
    source_id = _SOURCE_MAP.get(source_key, source_key)
    rows = []
    for record in raw:
        split_str = record.get("splitRatio") or record.get("split") or ""
        ratio = parse_ratio(split_str)
        rows.append(
            {
                "security_id": security_id,
                "effective_date": record.get("date"),
                "available_at": available_at,
                "source_id": source_id,
                "action_type": "split",
                "ratio_numerator": ratio[0],
                "ratio_denominator": ratio[1],
                "dividend_amount": None,
                "dividend_currency": None,
                "source_fetch_id": source_fetch_id,
                "raw_payload_hash": content_hash,
                "ingestion_run_id": ingestion_run_id,
                "content_hash": content_hash,
                "version_hash": "",
                "schema_version": 1,
                "parser_version": 1,
                "quality_status": "valid",
            }
        )
    if not rows:
        return pl.DataFrame()
    df = pl.DataFrame(rows)
    return df.with_columns(
        pl.col("effective_date").str.to_date("%Y-%m-%d"),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("ratio_numerator").cast(pl.Float64),
        pl.col("ratio_denominator").cast(pl.Float64),
        pl.col("dividend_amount").cast(pl.Float64),
        pl.col("dividend_currency").cast(pl.Utf8),
    )


def dividends_from_json(
    raw: list[dict[str, Any]],
    security_id: str,
    source_key: str,
    source_fetch_id: str,
    ingestion_run_id: str,
    content_hash: str,
    available_at: datetime,
) -> pl.DataFrame:
    source_id = _SOURCE_MAP.get(source_key, source_key)
    rows = []
    for record in raw:
        rows.append(
            {
                "security_id": security_id,
                "effective_date": record.get("date"),
                "available_at": available_at,
                "source_id": source_id,
                "action_type": "dividend",
                "ratio_numerator": None,
                "ratio_denominator": None,
                "dividend_amount": float(record.get("dividend", record.get("amount", 0))),
                "dividend_currency": record.get("currency"),
                "source_fetch_id": source_fetch_id,
                "raw_payload_hash": content_hash,
                "ingestion_run_id": ingestion_run_id,
                "content_hash": content_hash,
                "version_hash": "",
                "schema_version": 1,
                "parser_version": 1,
                "quality_status": "valid",
            }
        )
    if not rows:
        return pl.DataFrame()
    df = pl.DataFrame(rows)
    return df.with_columns(
        pl.col("effective_date").str.to_date("%Y-%m-%d"),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("ratio_numerator").cast(pl.Float64),
        pl.col("ratio_denominator").cast(pl.Float64),
        pl.col("dividend_amount").cast(pl.Float64),
        pl.col("dividend_currency").cast(pl.String),
    )


def parse_ratio(raw: str) -> tuple[float, float]:
    """Parse '2:1' → (2.0, 1.0), '1/5' → (1.0, 5.0)."""
    if not raw:
        return (1.0, 1.0)
    if ":" in raw:
        parts = raw.split(":")
        return (float(parts[0]), float(parts[1]))
    if "/" in raw:
        parts = raw.split("/")
        return (float(parts[0]), float(parts[1]))
    return (1.0, 1.0)
