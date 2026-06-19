from __future__ import annotations

from datetime import datetime
from typing import Any

import polars as pl


def bars_from_json(
    raw: list[dict[str, Any]],
    security_id: str,
    source_id: str,
    source_fetch_id: str,
    ingestion_run_id: str,
    content_hash: str,
    available_at: datetime,
    ingested_at: datetime | None = None,
) -> pl.DataFrame:
    rows = []
    for record in raw:
        rows.append(
            {
                "security_id": security_id,
                "effective_date": record.get("date"),
                "available_at": available_at,
                "source_id": source_id,
                "source_published_at": None,
                "ingested_at": ingested_at or available_at,
                "validated_at": None,
                "open": float(record.get("open", 0)),
                "high": float(record.get("high", 0)),
                "low": float(record.get("low", 0)),
                "close": float(record.get("close", 0)),
                "volume": int(record.get("volume", 0)),
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

    df = pl.DataFrame(rows)
    return df.with_columns(
        pl.col("effective_date").str.to_date("%Y-%m-%d"),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("source_published_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("ingested_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("validated_at").cast(pl.Datetime(time_zone="UTC")),
    )
