from __future__ import annotations

import json
import time
from datetime import date
from typing import Any

import httpx
import pytest

from alpha_lake.config import SourceConfig
from alpha_lake.connectors.base import (
    _CALL_LEDGER,
    BudgetExhaustedError,
    _prune_ledger,
    _reset_ledger,
    build_client,
    build_client_with_fallback,
    build_manifest,
    build_quota_exhausted_fetch,
    call_ledger_summary,
    check_budget,
    compute_content_hash,
    fetch_windowed,
)


def test_compute_content_hash():
    h = compute_content_hash(b"hello")
    assert isinstance(h, str)
    assert len(h) == 64


def test_quota_exhausted_fetch():
    rf = build_quota_exhausted_fetch(
        "test_source", "/endpoint", {"p": 1}, 1, "per-day limit (5/day)"
    )
    assert rf.manifest["status"] == "quota_exhausted"
    assert rf.manifest["http_status"] == 429
    assert rf.body == b""
    assert rf.manifest["quota_reason"] == "per-day limit (5/day)"


def test_budget_per_sec_exhausted():
    """A source with rate_limit_per_sec=1 should block the 2nd call."""
    _reset_ledger()
    cfg = SourceConfig(base_url="https://test.example.com", rate_limit_per_sec=1.0)
    check_budget(cfg)  # first call, ok
    time.sleep(0.01)  # tiny gap so timestamps differ
    with pytest.raises(BudgetExhaustedError, match="per-second"):
        check_budget(cfg)  # second call should be blocked


def test_budget_per_day_exhausted():
    """A source with rate_limit_per_day=2 should block the 3rd call."""
    _reset_ledger()
    cfg = SourceConfig(
        base_url="https://daily.example.com",
        rate_limit_per_sec=100.0,
        rate_limit_per_day=2,
    )
    check_budget(cfg)  # 1
    check_budget(cfg)  # 2
    with pytest.raises(BudgetExhaustedError, match="per-day"):
        check_budget(cfg)  # 3 should block


def test_budget_per_min_exhausted():
    """A source with rate_limit_per_min=1 should block the 2nd call."""
    _reset_ledger()
    cfg = SourceConfig(
        base_url="https://minute.example.com",
        rate_limit_per_sec=100.0,
        rate_limit_per_min=1,
    )
    check_budget(cfg)  # 1 — ok
    with pytest.raises(BudgetExhaustedError, match="per-minute"):
        check_budget(cfg)  # 2 — blocked


def test_ledger_persistence():
    """Verify call_ledger_summary returns counts."""
    _reset_ledger()
    cfg = SourceConfig(
        base_url="https://persist.example.com",
        rate_limit_per_sec=100.0,
        rate_limit_per_min=10,
        rate_limit_per_day=100,
    )
    check_budget(cfg)
    summary = call_ledger_summary()
    sid = "persist"
    assert sid in summary
    assert summary[sid]["calls_this_run"] >= 1


def test_prune_ledger():
    """Old entries are pruned."""
    now = time.time()
    _CALL_LEDGER["prune_test"] = [now - 90000, now - 1000, now]
    _prune_ledger("prune_test", now)
    assert len(_CALL_LEDGER["prune_test"]) <= 2  # the oldest (>24h) should be gone


def test_budget_no_limits():
    """Source with no per-min/per-day limits should not block."""
    _reset_ledger()
    cfg = SourceConfig(base_url="https://nolimits.example.com", rate_limit_per_sec=100.0)
    for _ in range(5):
        check_budget(cfg)  # should not raise
    assert True


# --- Phase 0.2 — Keyless / degraded fallback ---


def test_build_client_keyed():
    cfg = SourceConfig(api_key="secret123", base_url="https://keyed.example.com")
    client = build_client(cfg)
    assert client.headers.get("Authorization") == "Bearer secret123"
    assert str(client.base_url) == "https://keyed.example.com"


def test_build_client_keyless_with_fallback():
    cfg = SourceConfig(
        base_url="https://keyed.example.com",
        fallback_base_url="https://fallback.example.com",
        requires_key=True,
    )
    client = build_client(cfg)
    assert "Authorization" not in client.headers
    assert str(client.base_url) == "https://fallback.example.com"


def test_build_client_keyless_no_fallback():
    cfg = SourceConfig(base_url="https://nokey.example.com", requires_key=True)
    client = build_client(cfg)
    assert "Authorization" not in client.headers
    assert str(client.base_url) == "https://nokey.example.com"


def test_build_client_with_fallback_keyed():
    cfg = SourceConfig(api_key="k", base_url="https://keyed.example.com")
    client, mode = build_client_with_fallback(cfg)
    assert mode == "keyed"
    assert client.headers.get("Authorization") == "Bearer k"


def test_build_client_with_fallback_keyless():
    cfg = SourceConfig(
        base_url="https://keyed.example.com",
        fallback_base_url="https://fallback.example.com",
    )
    client, mode = build_client_with_fallback(cfg)
    assert mode == "keyless"
    assert "Authorization" not in client.headers
    assert str(client.base_url) == "https://fallback.example.com"


def test_manifest_key_mode_defaults():
    manifest = build_manifest("test", "/ep", None, b"data", 200, 1)
    assert manifest["key_mode"] == "keyed"


def test_manifest_key_mode_keyless():
    manifest = build_manifest("test", "/ep", None, b"data", 200, 1, key_mode="keyless")
    assert manifest["key_mode"] == "keyless"


# --- Phase 0.4 — SEC User-Agent compliance ---


def test_build_client_user_agent_with_contact():
    cfg = SourceConfig(
        base_url="https://data.sec.gov",
        contact_email="lake@example.com",
    )
    client = build_client(cfg)
    ua = client.headers.get("User-Agent", "")
    assert "alpha-lake/" in ua
    assert "lake@example.com" in ua


def test_build_client_user_agent_without_contact():
    cfg = SourceConfig(base_url="https://data.sec.gov")
    client = build_client(cfg)
    ua = client.headers.get("User-Agent", "")
    assert "alpha-lake" not in ua


# --- Phase 0.3 — Chunked-window fetch helper ---


@pytest.mark.asyncio
async def test_fetch_windowed_single_chunk():
    """When the range fits in one chunk, only one fetch is made."""
    calls: list[dict[str, Any]] = []

    class _MockClient:
        base_url = "http://test"

        async def get(self, endpoint, params=None):  # noqa: ARG002
            calls.append({"endpoint": endpoint, "params": params})
            return httpx.Response(200, json=[{"id": "a", "val": 1}])

    client: Any = _MockClient()
    results = await fetch_windowed(
        client, "/data", start=date(2025, 1, 1), end=date(2025, 1, 5), chunk_days=30
    )
    assert len(results) == 1
    assert len(calls) == 1
    assert results[0].manifest["http_status"] == 200


@pytest.mark.asyncio
async def test_fetch_windowed_multiple_chunks():
    """A 90-day range with chunk_days=30 produces 3 chunks."""
    calls: list[dict[str, Any]] = []

    class _MockClient:
        base_url = "http://test"

        async def get(self, endpoint, params=None):  # noqa: ARG002
            calls.append({"endpoint": endpoint, "params": params})
            return httpx.Response(200, json=[{"id": str(len(calls)), "val": len(calls)}])

    client: Any = _MockClient()
    results = await fetch_windowed(
        client, "/data", start=date(2025, 1, 1), end=date(2025, 3, 31), chunk_days=30
    )
    assert len(results) == 3
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_fetch_windowed_dedupe():
    """Injected duplicate is removed when dedupe_key is set."""
    calls = 0

    class _MockClient:
        base_url = "http://test"

        async def get(self, _endpoint, **kwargs):  # noqa: ARG002
            nonlocal calls
            calls += 1
            return httpx.Response(200, json=[{"id": "dup", "val": calls}])

    client: Any = _MockClient()
    results = await fetch_windowed(
        client,
        "/data",
        start=date(2025, 1, 1),
        end=date(2025, 2, 1),
        chunk_days=15,
        dedupe_key="id",
    )
    total_records = 0
    for rf in results:
        data = json.loads(rf.body)
        total_records += len(data)
    assert total_records == 1  # only one "dup" survives across chunks


@pytest.mark.asyncio
async def test_fetch_windowed_custom_param_names():
    """Custom start_param/end_param are used in query params."""
    calls: list[dict[str, Any]] = []

    class _MockClient:
        base_url = "http://test"

        async def get(self, endpoint, params=None):  # noqa: ARG002
            if params is not None:
                calls.append(params)
            return httpx.Response(200, json=[{"x": "y"}])

    client: Any = _MockClient()
    await fetch_windowed(
        client,
        "/data",
        start=date(2025, 6, 1),
        end=date(2025, 6, 2),
        chunk_days=10,
        start_param="from_date",
        end_param="to_date",
    )
    p: dict[str, Any] = calls[0] if calls[0] else {}
    assert p.get("from_date") == "2025-06-01"
    assert p.get("to_date") == "2025-06-02"
