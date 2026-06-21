from __future__ import annotations

import os
import tomllib

import pydantic

from alpha_lake.secrets import get_store


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
    access_key: str = ""
    secret_key: str = ""

    @pydantic.model_validator(mode="after")
    def _fill_from_env(self) -> S3Config:
        if not self.access_key:
            self.access_key = os.environ.get("RUSTFS_ACCESS_KEY", "rustfsadmin")
        if not self.secret_key:
            self.secret_key = os.environ.get("RUSTFS_SECRET_KEY", "rustfsadmin")
        return self


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
    canonical_data_path: str = ""
    raw_archive_uri: str = ""
    calendar_version: str = ""


class RootConfig(pydantic.BaseModel):
    lake: LakeConfig
    s3: S3Config = S3Config()
    quality: dict[str, QualityConfig] = {}
    reconcile: dict[str, ReconciliationConfig] = {}
    sources: dict[str, SourceConfig] = {}
    source_datasets: dict[str, dict[str, SourceDatasetConfig]] = {}
    precedence: dict[str, list[str]] = {}


_config: RootConfig | None = None


def load_config(path: str | None = None) -> RootConfig:
    global _config
    if path is None:
        path = os.environ.get("ALPHA_LAKE_CONFIG", "config/stack.toml")

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    store = get_store()
    for source_id in raw.get("sources", {}):
        stored = store.get(f"{source_id}_api_key")
        if stored:
            raw["sources"][source_id].setdefault("api_key", stored)

    _config = RootConfig.model_validate(raw)
    return _config


def get_config() -> RootConfig:
    assert _config is not None, "config not loaded — call load_config() first"
    return _config
