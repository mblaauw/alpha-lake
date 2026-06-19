from __future__ import annotations

import datetime
from typing import Annotated

import pydantic
from pydantic import StringConstraints


from typing import Annotated

from pydantic import StringConstraints

SecurityId = Annotated[str, StringConstraints(pattern=r"^sec_[a-z0-9]+$")]
"""Deterministic security identifier. Never random or symbol-prefixed."""

SourceId = Annotated[str, StringConstraints(pattern=r"^[a-z_]+$")]
"""Source identifier (e.g. 'eodhd', 'tiingo', 'sec')."""


class TemporalFields(pydantic.BaseModel):
    effective_date: datetime.date
    available_at: datetime.datetime
    source_published_at: datetime.datetime | None = None
    ingested_at: datetime.datetime | None = None
    validated_at: datetime.datetime | None = None


class LineageFields(pydantic.BaseModel):
    security_id: str
    source_id: str
    schema_version: int = 1
    parser_version: int = 1
    source_fetch_id: str = ""
    raw_payload_hash: str = ""
    ingestion_run_id: str = ""
    content_hash: str = ""
    version_hash: str = ""
    quality_status: str = "valid"
