from __future__ import annotations

import datetime

import patito as pt


class IPOEventFact(pt.Model):
    model_config = {"coerce_nulls": True}
    symbol: str
    effective_date: datetime.date
    available_at: datetime.datetime
    source_id: str
    company_name: str
    exchange: str = ""
    offer_date: datetime.date | None = None
    status: str = ""
    source_fetch_id: str
    raw_payload_hash: str
    ingestion_run_id: str
    content_hash: str
    version_hash: str
    schema_version: int = 1
    parser_version: int = 1
    quality_status: str = "valid"
