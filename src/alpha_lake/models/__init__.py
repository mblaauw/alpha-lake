from __future__ import annotations

from typing import Annotated

from pydantic import StringConstraints

SecurityId = Annotated[str, StringConstraints(pattern=r"^sec_[a-z0-9]+$")]
"""Deterministic security identifier. Never random or symbol-prefixed."""

SourceId = Annotated[str, StringConstraints(pattern=r"^[a-z_]+$")]
"""Source identifier (e.g. 'eodhd', 'tiingo', 'sec')."""

