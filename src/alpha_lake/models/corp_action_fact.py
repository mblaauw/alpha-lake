import datetime

import patito as pt


class CorpActionFact(pt.Model):
    security_id: str
    effective_date: datetime.date
    available_at: datetime.datetime
    source_id: str
    action_type: str
    ratio_numerator: float | None = None
    ratio_denominator: float | None = None
    dividend_amount: float | None = None
    dividend_currency: str | None = None
    source_fetch_id: str
    raw_payload_hash: str
    ingestion_run_id: str
    content_hash: str
    version_hash: str
    schema_version: int = 1
    parser_version: int = 1
    quality_status: str = "valid"
