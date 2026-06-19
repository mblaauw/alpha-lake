from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from alpha_lake.config import SourceConfig


@dataclass
class RawFetch:
    manifest: dict[str, Any]
    body: bytes


def compute_content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_manifest(
    source_id: str,
    endpoint: str,
    params: dict[str, Any] | None,
    raw_bytes: bytes,
    http_status: int,
    parser_version: int,
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "endpoint": endpoint,
        "request_params_json": json.dumps(params or {}, sort_keys=True),
        "request_params_hash": hashlib.sha256(
            json.dumps(params or {}, sort_keys=True).encode()
        ).hexdigest(),
        "ingest_ts": None,
        "http_status": http_status,
        "content_hash": compute_content_hash(raw_bytes),
        "content_type": "",
        "byte_size": len(raw_bytes),
        "parser_version_intended": parser_version,
    }


def build_client(cfg: SourceConfig) -> httpx.AsyncClient:
    headers = {}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"
    return httpx.AsyncClient(base_url=cfg.base_url, headers=headers, timeout=30.0)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
)
async def fetch_with_retry(
    client: httpx.AsyncClient,
    endpoint: str,
    params: dict[str, Any] | None = None,
) -> httpx.Response:
    return await client.get(endpoint, params=params)
