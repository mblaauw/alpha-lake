from __future__ import annotations

import contextlib
import hashlib
import json
import os
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from alpha_lake.config import SourceConfig


@dataclass
class RawFetch:
    manifest: dict[str, Any]
    body: bytes


# --- Sliding-window budget tracker ---

_CALL_LEDGER: dict[str, list[float]] = defaultdict(list)
"""source_id -> list of Unix timestamps of recent calls (file-backed)."""

_LEDGER_PATH: str | None = None


def _ledger_path() -> str:
    global _LEDGER_PATH
    if _LEDGER_PATH is None:
        state_dir = os.environ.get("ALPHA_LAKE_STATE_DIR", "/tmp/alpha_lake_state")
        os.makedirs(state_dir, exist_ok=True)
        _LEDGER_PATH = os.path.join(state_dir, "call_ledger.json")
    return _LEDGER_PATH


def _persist_ledger() -> None:
    path = _ledger_path()
    with open(path, "w") as f:
        json.dump({k: v for k, v in _CALL_LEDGER.items()}, f)


def _reset_ledger() -> None:
    _CALL_LEDGER.clear()
    path = _ledger_path()
    with contextlib.suppress(FileNotFoundError):
        os.remove(path)


def _load_ledger() -> None:
    path = _ledger_path()
    try:
        with open(path) as f:
            data = json.load(f)
            for source_id, timestamps in data.items():
                _CALL_LEDGER[source_id] = timestamps
    except FileNotFoundError, json.JSONDecodeError:
        pass


def _prune_ledger(source_id: str, now: float) -> None:
    """Remove timestamps older than 24 hours."""
    cutoff = now - 86400
    _CALL_LEDGER[source_id] = [t for t in _CALL_LEDGER[source_id] if t > cutoff]


def _count_in_window(source_id: str, now: float, window_secs: int) -> int:
    cutoff = now - window_secs
    return sum(1 for t in _CALL_LEDGER[source_id] if t > cutoff)


def _record_call(source_id: str, now: float) -> None:
    _CALL_LEDGER[source_id].append(now)
    _prune_ledger(source_id, now)
    _persist_ledger()


class BudgetExhaustedError(Exception):
    """Raised when the per-source budget is exhausted for the current window."""

    def __init__(self, source_id: str, reason: str) -> None:
        self.source_id = source_id
        self.reason = reason
        super().__init__(f"Budget exhausted for {source_id}: {reason}")


def check_budget(cfg: SourceConfig) -> None:
    """Check per-source rate budgets and raise BudgetExhaustedError if exceeded.

    Checks per-second, per-minute, and per-day limits in order.
    On CI/test the file-backed ledger is loaded lazily.
    """
    if not _CALL_LEDGER:
        _load_ledger()

    source_id = cfg.base_url.split("//")[-1].split(".")[0] if cfg.base_url else "unknown"
    now = time.time()
    _prune_ledger(source_id, now)

    if cfg.rate_limit_per_sec > 0:
        window_sec = 1
        count = _count_in_window(source_id, now, window_sec)
        if count >= int(cfg.rate_limit_per_sec):
            raise BudgetExhaustedError(source_id, f"per-second limit ({cfg.rate_limit_per_sec}/s)")

    if cfg.rate_limit_per_min is not None:
        count = _count_in_window(source_id, now, 60)
        if count >= cfg.rate_limit_per_min:
            raise BudgetExhaustedError(
                source_id, f"per-minute limit ({cfg.rate_limit_per_min}/min)"
            )

    if cfg.rate_limit_per_day is not None:
        count = _count_in_window(source_id, now, 86400)
        if count >= cfg.rate_limit_per_day:
            raise BudgetExhaustedError(source_id, f"per-day limit ({cfg.rate_limit_per_day}/day)")

    _record_call(source_id, now)


def call_ledger_summary(source_id: str | None = None) -> dict[str, dict[str, int]]:
    """Return per-source call counts.

    Returns dict mapping source_id -> {calls_this_run, calls_last_min,
    calls_last_day}.
    """
    _load_ledger()
    now = time.time()
    summary: dict[str, dict[str, int]] = {}
    targets = [source_id] if source_id else list(_CALL_LEDGER.keys())
    for sid in targets:
        _prune_ledger(sid, now)
        last_min = _count_in_window(sid, now, 60)
        last_day = _count_in_window(sid, now, 86400)
        summary[sid] = {
            "calls_this_run": len(_CALL_LEDGER.get(sid, [])),
            "calls_last_min": last_min,
            "calls_last_day": last_day,
        }
    return summary


def build_quota_exhausted_fetch(
    source_id: str,
    endpoint: str,
    params: dict[str, Any] | None,
    parser_version: int,
    reason: str,
) -> RawFetch:
    """Build a RawFetch representing a quota-exhausted outcome."""
    return RawFetch(
        manifest={
            "source_id": source_id,
            "endpoint": endpoint,
            "request_params_json": json.dumps(params or {}, sort_keys=True),
            "request_params_hash": hashlib.sha256(
                json.dumps(params or {}, sort_keys=True).encode()
            ).hexdigest(),
            "http_status": 429,
            "content_hash": "",
            "content_type": "",
            "byte_size": 0,
            "parser_version_intended": parser_version,
            "status": "quota_exhausted",
            "quota_reason": reason,
        },
        body=b"",
    )


# --- Content hashing ---


def compute_content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_manifest(
    source_id: str,
    endpoint: str,
    params: dict[str, Any] | None,
    raw_bytes: bytes,
    http_status: int,
    parser_version: int,
    ingest_ts: str | None = None,
    key_mode: str = "keyed",
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "endpoint": endpoint,
        "request_params_json": json.dumps(params or {}, sort_keys=True),
        "request_params_hash": hashlib.sha256(
            json.dumps(params or {}, sort_keys=True).encode()
        ).hexdigest(),
        "ingest_ts": ingest_ts,
        "http_status": http_status,
        "content_hash": compute_content_hash(raw_bytes),
        "content_type": "",
        "byte_size": len(raw_bytes),
        "parser_version_intended": parser_version,
        "key_mode": key_mode,
    }


def build_client(cfg: SourceConfig) -> httpx.AsyncClient:
    """Build an httpx client for the given source config.

    If ``cfg.api_key`` is empty and ``cfg.fallback_base_url`` is set, uses
    the keyless fallback endpoint with reduced rate limits. The caller should
    call ``check_budget(cfg)`` separately — this function does not enforce
    budgets.
    """
    headers = {}

    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"

    if cfg.contact_email:
        headers["User-Agent"] = f"alpha-lake/0.1.0 ({cfg.contact_email})"

    return httpx.AsyncClient(
        base_url=cfg.base_url if cfg.api_key else (cfg.fallback_base_url or cfg.base_url),
        headers=headers,
        timeout=30.0,
    )


def build_client_with_fallback(cfg: SourceConfig) -> tuple[httpx.AsyncClient, str]:
    """Build client and return ``(client, key_mode)``.

    *key_mode* is ``"keyed"`` when an API key is present, ``"keyless"`` when
    the fallback is used, or ``"keyless"`` when no key is available.
    """
    key_mode = "keyed" if cfg.api_key else "keyless"
    return build_client(cfg), key_mode


async def fetch_windowed(
    client: httpx.AsyncClient,
    endpoint: str,
    params: dict[str, Any] | None = None,
    *,
    start: date,
    end: date,
    start_param: str = "start",
    end_param: str = "end",
    chunk_days: int = 30,
    dedupe_key: str = "",
    source_id: str | None = None,
    parser_version: int = 1,
) -> list[RawFetch]:
    """Fetch a date range in chunks, dedupe, and return per-chunk RawFetches.

    Walks ``[start, end]`` in ``chunk_days`` windows, fetches each window,
    dedupes across the full set by ``dedupe_key``, and returns a list of
    ``RawFetch`` objects (one per chunk). Each chunk is archived separately
    so replay stays deterministic per chunk.

    ``start_param`` / ``end_param`` control the query param names for the
    date range (different APIs use different names). When ``dedupe_key`` is
    empty, no deduplication is performed.
    """
    chunks: list[RawFetch] = []
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=chunk_days - 1), end)
        chunk_params = dict(params or {})
        chunk_params[start_param] = cursor.isoformat()
        chunk_params[end_param] = chunk_end.isoformat()
        response = await fetch_with_retry(client, endpoint, params=chunk_params)
        raw_bytes = response.content
        manifest = build_manifest(
            source_id or "windowed",
            endpoint,
            chunk_params,
            raw_bytes,
            response.status_code,
            parser_version,
        )
        chunks.append(RawFetch(manifest=manifest, body=raw_bytes))
        cursor = chunk_end + timedelta(days=1)

    if dedupe_key and len(chunks) > 1:
        seen: set[str] = set()
        for rf in chunks:
            try:
                data = json.loads(rf.body)
                if isinstance(data, list):
                    data = [r for r in data if r.get(dedupe_key) not in seen]
                    for r in data:
                        val = r.get(dedupe_key)
                        if val:
                            seen.add(val)
                    rf.body = json.dumps(data).encode()
            except json.JSONDecodeError, TypeError:
                pass

    return chunks


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
