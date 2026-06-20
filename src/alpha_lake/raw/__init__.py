from __future__ import annotations

import hashlib

import zstd  # ty: ignore

from alpha_lake.config import get_config
from alpha_lake.storage import get_blob_store


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
    store = get_blob_store(cfg.lake.raw_archive_uri)
    return store.exists(path)


def archive(data: bytes) -> str:
    cfg = get_config()
    h = content_hash(data)
    if exists(h):
        return h
    path = _store_path(h)
    compressed = compress(data)

    store = get_blob_store(cfg.lake.raw_archive_uri)
    store.write_bytes(path, compressed)
    return h


def read_raw(hash_val: str) -> bytes:
    cfg = get_config()
    path = _store_path(hash_val)
    store = get_blob_store(cfg.lake.raw_archive_uri)
    compressed = store.read_bytes(path)
    return decompress(compressed)
