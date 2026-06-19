from __future__ import annotations

import datetime

import patito as pt
from patito import Field


class BarFact(pt.Model):
    security_id: str
    effective_date: datetime.date
    available_at: datetime.datetime
    source_id: str
    source_published_at: datetime.datetime | None = None
    ingested_at: datetime.datetime | None = None
    validated_at: datetime.datetime | None = None
    open: float = Field(ge=0)
    high: float = Field(ge=0)
    low: float = Field(ge=0)
    close: float = Field(ge=0)
    volume: int = Field(ge=0)
    source_fetch_id: str
    raw_payload_hash: str
    ingestion_run_id: str
    content_hash: str
    version_hash: str
    schema_version: int = 1
    parser_version: int = 1
    quality_status: str = "valid"
