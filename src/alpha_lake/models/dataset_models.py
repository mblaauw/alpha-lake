import datetime

import patito as pt
from patito import Field


class FundamentalFact(pt.Model):
    model_config = {"coerce_nulls": True}
    security_id: str
    effective_date: datetime.date
    available_at: datetime.datetime
    source_id: str
    source_published_at: datetime.datetime | None = None
    ingested_at: datetime.datetime | None = None
    validated_at: datetime.datetime | None = None
    fiscal_period: str
    period_kind: str
    period_end: datetime.date
    measurement_kind: str
    statement_type: str
    line_item: str
    value: float
    currency: str = "USD"
    source_currency: str = "USD"
    unit: str = "raw"
    source_priority: int | None = None
    source_fetch_id: str
    raw_payload_hash: str
    ingestion_run_id: str
    content_hash: str
    version_hash: str
    schema_version: int = 1
    parser_version: int = 1
    quality_status: str = "valid"


class InsiderTxFact(pt.Model):
    model_config = {"coerce_nulls": True}
    security_id: str
    effective_date: datetime.date
    available_at: datetime.datetime
    source_id: str
    filer_cik: str
    issuer_cik: str
    transaction_code: str
    shares: float
    price: float
    value: float
    source_fetch_id: str
    raw_payload_hash: str
    ingestion_run_id: str
    content_hash: str
    version_hash: str
    schema_version: int = 1
    parser_version: int = 1
    quality_status: str = "valid"


class NewsArticleFact(pt.Model):
    model_config = {"coerce_nulls": True}
    article_id: str
    effective_date: datetime.date
    available_at: datetime.datetime
    source_id: str
    title: str
    description: str | None = None
    url: str
    text_hash: str
    published_at: datetime.datetime | None = None
    source_name: str
    source_fetch_id: str
    raw_payload_hash: str
    ingestion_run_id: str
    content_hash: str
    version_hash: str
    schema_version: int = 1
    parser_version: int = 1
    quality_status: str = "valid"


class SocialPostFact(pt.Model):
    model_config = {"coerce_nulls": True}
    post_id_hash: str
    effective_date: datetime.date
    available_at: datetime.datetime
    source_id: str
    platform: str
    venue: str
    parent_id_hash: str | None = None
    text_hash: str
    published_at: datetime.datetime | None = None
    engagement_json: str | None = None
    source_fetch_id: str
    raw_payload_hash: str
    ingestion_run_id: str
    content_hash: str
    version_hash: str
    schema_version: int = 1
    parser_version: int = 1
    quality_status: str = "valid"


class EarningsEventFact(pt.Model):
    model_config = {"coerce_nulls": True}
    security_id: str
    effective_date: datetime.date
    available_at: datetime.datetime
    source_id: str
    report_date: datetime.date
    session: str = "regular"
    source_fetch_id: str
    raw_payload_hash: str
    ingestion_run_id: str
    content_hash: str
    version_hash: str
    schema_version: int = 1
    parser_version: int = 1
    quality_status: str = "valid"


class EntityMentionFact(pt.Model):
    model_config = {"coerce_nulls": True}
    mention_id: str
    effective_date: datetime.date
    available_at: datetime.datetime
    text_item_id: str
    text_item_type: str
    security_id: str
    entity_name: str
    entity_type: str
    confidence: float = Field(ge=0, le=1)
    match_method: str
    source_fetch_id: str
    raw_payload_hash: str
    ingestion_run_id: str
    content_hash: str
    version_hash: str
    schema_version: int = 1
    parser_version: int = 1
    quality_status: str = "valid"


class SentimentAnnotationFact(pt.Model):
    model_config = {"coerce_nulls": True}
    annotation_id: str
    effective_date: datetime.date
    available_at: datetime.datetime
    source_id: str
    annotation_kind: str
    sentiment_score: float | None = None
    sentiment_label: str = ""
    model_version: str | None = None
    prompt_version: str | None = None
    taxonomy_version: str | None = None
    input_text_hash: str | None = None
    source_dataset_version: str | None = None
    security_id: str = ""
    source_fetch_id: str
    raw_payload_hash: str
    ingestion_run_id: str
    content_hash: str
    version_hash: str
    schema_version: int = 1
    parser_version: int = 1
    quality_status: str = "valid"


class SocialAttentionFact(pt.Model):
    model_config = {"coerce_nulls": True}
    security_id: str
    effective_date: datetime.date
    available_at: datetime.datetime
    source_id: str
    cohort: str
    mentions: int = Field(ge=0)
    mentions_24h_ago: int = Field(ge=0)
    upvotes: int | None = Field(None, ge=0)
    rank: int | None = Field(None, ge=1)
    rank_24h_ago: int | None = Field(None, ge=1)
    name: str | None = None
    source_fetch_id: str
    raw_payload_hash: str
    ingestion_run_id: str
    content_hash: str
    version_hash: str
    schema_version: int = 1
    parser_version: int = 2
    quality_status: str = "valid"
