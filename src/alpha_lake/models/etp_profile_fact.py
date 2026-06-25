from __future__ import annotations

import datetime

import patito as pt


class ETPProfileFact(pt.Model):
    model_config = {"coerce_nulls": True}
    security_id: str
    effective_date: datetime.date
    available_at: datetime.datetime
    source_id: str
    name: str
    asset_type: str = "ETF"
    net_assets: float | None = None
    expense_ratio: float | None = None
    dividend_yield: float | None = None
    source_fetch_id: str
    raw_payload_hash: str
    ingestion_run_id: str
    content_hash: str
    version_hash: str
    schema_version: int = 1
    parser_version: int = 1
    quality_status: str = "valid"
