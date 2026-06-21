from __future__ import annotations

import datetime

import patito as pt
from patito import Field


class AnalystEstimateFact(pt.Model):
    model_config = {"coerce_nulls": True}
    security_id: str
    effective_date: datetime.date
    available_at: datetime.datetime
    source_id: str
    strong_buy: int = Field(ge=0)
    buy: int = Field(ge=0)
    hold: int = Field(ge=0)
    sell: int = Field(ge=0)
    strong_sell: int = Field(ge=0)
    target_mean: float | None = None
    target_high: float | None = None
    target_low: float | None = None
    source_fetch_id: str
    raw_payload_hash: str
    ingestion_run_id: str
    content_hash: str
    version_hash: str
    schema_version: int = 1
    parser_version: int = 1
    quality_status: str = "valid"
