from __future__ import annotations

import datetime

import patito as pt
from patito import Field


class RelativeStrengthFact(pt.Model):
    model_config = {"coerce_nulls": True}
    security_id: str
    effective_date: datetime.date
    available_at: datetime.datetime
    window: int
    source_id: str = "derived"
    rs_return: float | None = None
    rs_percentile: float | None = Field(None, ge=0, le=100)
    source_fetch_id: str = ""
    raw_payload_hash: str = ""
    ingestion_run_id: str = ""
    content_hash: str = ""
    version_hash: str = ""
    schema_version: int = 1
    parser_version: int = 1
    quality_status: str = "valid"
