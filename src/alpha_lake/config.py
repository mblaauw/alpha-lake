from __future__ import annotations

import os
from pathlib import Path

import pydantic
import toml


class S3Config(pydantic.BaseModel):
    endpoint: str = "rustfs:9000"
    url_style: str = "path"
    use_ssl: bool = False


class QualityConfig(pydantic.BaseModel):
    max_staleness_days: int = 7
    halt_on_stale_prices: bool = False


class LakeConfig(pydantic.BaseModel):
    runtime: str = "stack"
    catalog: str = ""
    data_path: str = ""


class RootConfig(pydantic.BaseModel):
    lake: LakeConfig
    s3: S3Config = S3Config()
    quality: dict[str, QualityConfig] = {}


def load_config(path: str | None = None) -> RootConfig:
    if path is None:
        path = os.environ.get("ALPHA_LAKE_CONFIG", "config/stack.toml")
    raw = toml.load(Path(path))
    return RootConfig.model_validate(raw)
