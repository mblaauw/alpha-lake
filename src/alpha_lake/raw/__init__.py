from __future__ import annotations

import hashlib
from pathlib import Path

import zstd  # ty: ignore

from alpha_lake.config import get_config


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _store_path(hash_val: str) -> str:
    return f"raw/{hash_val[:2]}/{hash_val[2:4]}/{hash_val}.zst"


def compress(data: bytes) -> bytes:
    return zstd.compress(data, 3)


def decompress(data: bytes) -> bytes:
    return zstd.decompress(data)


def exists(hash_val: str) -> bool:
    cfg = get_config()
    path = _store_path(hash_val)
    return (Path(cfg.lake.data_path) / path).exists()


def archive(data: bytes) -> str:
    cfg = get_config()
    h = content_hash(data)
    if exists(h):
        return h
    path = _store_path(h)
    compressed = compress(data)

    base = Path(cfg.lake.data_path)
    full_path = base / path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(compressed)
    return h


def read_raw(hash_val: str) -> bytes:
    cfg = get_config()
    path = _store_path(hash_val)
    base = Path(cfg.lake.data_path)
    compressed = (base / path).read_bytes()
    return decompress(compressed)
