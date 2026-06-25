from __future__ import annotations

import datetime

import patito as pt


class FundamentalMetricFact(pt.Model):
    model_config = {"coerce_nulls": True}
    security_id: str
    metric_id: str
    metric_version: str
    category: str
    period_kind: str
    period_end: datetime.date
    available_at: datetime.datetime
    value: float | None = None
    unit: str
    currency: str | None = None
    source_currency: str | None = None
    source_period_ends: str
    source_version_hashes: str
    calculation_basis: str
    quality_status: str = "valid"
    calculation_version: str
    ingestion_run_id: str
    source_id: str = "derived"
    source_fetch_id: str = ""
    raw_payload_hash: str = ""
    content_hash: str = ""
    version_hash: str = ""
    schema_version: int = 1
    parser_version: int = 1
