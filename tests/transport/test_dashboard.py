"""Smoke tests for dashboard endpoints.

These tests use FastAPI TestClient against the running app with
``dashboard_enabled`` temporarily toggled.
"""

from __future__ import annotations

import subprocess

import pytest
from fastapi.testclient import TestClient  # type: ignore[unresolved-import]

from alpha_lake import config as _cfg_mod
from alpha_lake.config import LakeConfig, RootConfig, S3Config, TransportConfig
from alpha_lake.interpretation.fundamentals_glossary import FUNDAMENTAL_GLOSSARY
from alpha_lake.transport.app import app

client = TestClient(app)


@pytest.fixture
def _enable_dashboard():
    cfg = RootConfig(
        lake=LakeConfig(
            runtime="embedded",
            catalog="ducklake:sqlite::memory:",
            canonical_data_path="/tmp/lake/",
            raw_archive_uri="/tmp/lake/",
            calendar_version="4.13.2",
        ),
        transport=TransportConfig(dashboard_enabled=True),
        s3=S3Config(),
    )
    saved = _cfg_mod._config
    _cfg_mod._config = cfg
    from alpha_lake.transport import app as tapp

    tapp._DASHBOARD_ENABLED = None
    yield
    _cfg_mod._config = saved


def _stack_available() -> bool:
    try:
        result = subprocess.run(
            ["docker", "compose", "ps", "--services", "--filter", "status=running"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        services = result.stdout.strip().split("\n")
        return "postgres" in services
    except subprocess.SubprocessError, FileNotFoundError, OSError:
        return False


def test_home_returns_404_when_disabled():
    """Dashboard is disabled by default — / should return 404."""
    resp = client.get("/")
    assert resp.status_code == 404


def test_dashboard_api_returns_404_when_disabled():
    """Dashboard API returns 404 when dashboard_enabled=false."""
    resp = client.get("/v1/dashboard/datasets")
    assert resp.status_code == 404


@pytest.mark.skipif(not _stack_available(), reason="Docker stack required")
def test_health_endpoint_returns_json():
    """V1 /v1/health should return a JSON response (without auth)."""
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)


def test_static_files_served():
    """Static files should be served under /static/."""
    for path in [
        "/static/index.html",
        "/static/styles.css",
        "/static/app.js",
        "/static/manifest.webmanifest",
    ]:
        resp = client.get(path)
        assert resp.status_code == 200, f"{path} not found"


def test_service_worker_served():
    """Service worker should be served at /service-worker.js."""
    resp = client.get("/service-worker.js")
    assert resp.status_code == 200
    assert b"self." in resp.content


def test_icons_served():
    """Icon files should be served under /static/icons/."""
    for path in ["/static/icons/icon-192.svg", "/static/icons/icon-512.svg"]:
        resp = client.get(path)
        assert resp.status_code == 200, f"{path} not found"


def test_bars_requires_auth():
    """Existing /v1/bars should require API key."""
    resp = client.get("/v1/bars?symbol=AAPL")
    assert resp.status_code == 401


def test_dashboard_fundamentals_glossary_returns_entries(_enable_dashboard):
    resp = client.get("/v1/dashboard/fundamentals/glossary")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == len(FUNDAMENTAL_GLOSSARY)
    ids = {e["metric_id"] for e in data}
    assert "fundamentals.scale.revenue_ttm" in ids
    assert "fundamentals.valuation.price_to_earnings_ttm" in ids


def test_dashboard_fundamentals_glossary_category_filter(_enable_dashboard):
    resp = client.get("/v1/dashboard/fundamentals/glossary?categories=Valuation")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    for entry in data:
        assert entry["category"] == "Valuation"
    assert len(data) == 3
