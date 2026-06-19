from __future__ import annotations

import os
from pathlib import Path

import pydantic
import toml


class SourceConfig(pydantic.BaseModel):
    api_key: str = ""
    base_url: str = ""
    rate_limit_per_sec: float = 10.0
    max_retries: int = 3


class SourceDatasetConfig(pydantic.BaseModel):
    enabled: bool = True
    parser_version: int = 1
    endpoint_override: str | None = None


class S3Config(pydantic.BaseModel):
    endpoint: str = "rustfs:9000"
    url_style: str = "path"
    use_ssl: bool = False


class QualityConfig(pydantic.BaseModel):
    max_staleness_days: int = 7
    halt_on_stale_prices: bool = False


class ReconciliationConfig(pydantic.BaseModel):
    price_diff_pct: float = 1.0
    volume_diff_pct: float = 5.0
    cross_source_enabled: bool = False


class LakeConfig(pydantic.BaseModel):
    runtime: str = "stack"
    catalog: str = ""
    data_path: str = ""


class RootConfig(pydantic.BaseModel):
    lake: LakeConfig
    s3: S3Config = S3Config()
    quality: dict[str, QualityConfig] = {}
    reconcile: dict[str, ReconciliationConfig] = {}
    sources: dict[str, SourceConfig] = {}
    source_datasets: dict[str, dict[str, SourceDatasetConfig]] = {}


_config: RootConfig | None = None


def load_config(path: str | None = None) -> RootConfig:
    global _config
    if path is None:
        path = os.environ.get("ALPHA_LAKE_CONFIG", "config/stack.toml")

    raw = toml.load(Path(path))

    api_key = os.environ.get("ALPHA_LAKE_EODHD_API_KEY", "")
    if api_key and "eodhd" not in raw.get("sources", {}):
        raw.setdefault("sources", {})["eodhd"] = {}
        raw["sources"]["eodhd"].setdefault("api_key", api_key)

    _config = RootConfig.model_validate(raw)
    return _config


def get_config() -> RootConfig:
    assert _config is not None, "config not loaded — call load_config() first"
    return _config
