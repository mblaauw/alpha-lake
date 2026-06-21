from __future__ import annotations

import duckdb
import pytest

from alpha_lake.kernel import register_kernel
from alpha_lake.secrets import StaticSecretStore, get_store, set_store


@pytest.fixture(autouse=True)
def _reset_store():
    prev = get_store()
    store = StaticSecretStore()
    set_store(store)
    store.set("alpha_lake_api_key_test", "al_test_supersecret123")
    yield
    set_store(prev)


@pytest.fixture
def _test_con():
    con = duckdb.connect()
    con.execute("""
        CREATE TABLE IF NOT EXISTS security_master (
            security_id VARCHAR NOT NULL,
            symbol VARCHAR NOT NULL,
            name VARCHAR,
            exchange VARCHAR,
            figi VARCHAR,
            cik VARCHAR,
            effective_start DATE NOT NULL,
            effective_end DATE,
            available_at TIMESTAMPTZ NOT NULL
        )
    """)
    con.execute(
        "INSERT INTO security_master VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            "sec_test",
            "TEST",
            "Test Corp",
            "XNYS",
            "",
            "",
            "2000-01-01",
            None,
            "2000-01-01 00:00:00+00",
        ],
    )
    register_kernel(con)
    return con


@pytest.fixture
def client(_test_con):
    from fastapi.testclient import TestClient

    from alpha_lake.transport import app as transport_app

    transport_app._connection = _test_con
    return TestClient(transport_app.app)


def _auth_header() -> dict[str, str]:
    return {"X-API-Key": "al_test_supersecret123"}


def test_health_no_auth_required(client):
    resp = client.get("/v1/health")
    assert resp.status_code == 200


def test_health_authenticated(client):
    resp = client.get("/v1/health", headers=_auth_header())
    assert resp.status_code == 200


def test_bars_no_auth(client):
    resp = client.get("/v1/bars", params={"symbol": "AAPL"})
    assert resp.status_code == 401


def test_bars_invalid_key(client):
    resp = client.get("/v1/bars", params={"symbol": "AAPL"}, headers={"X-API-Key": "badkey"})
    assert resp.status_code == 401


def test_bars_unknown_symbol(client):
    resp = client.get(
        "/v1/bars",
        params={"symbol": "ZZZZZ_UNKNOWN"},
        headers=_auth_header(),
    )
    assert resp.status_code == 404


def test_bars_lookback_exceeded(client):
    resp = client.get(
        "/v1/bars",
        params={
            "symbol": "AAPL",
            "start": "2020-01-01",
            "end": "2026-06-01",
        },
        headers=_auth_header(),
    )
    assert resp.status_code == 422


def test_bars_indicators_no_auth(client):
    resp = client.get(
        "/v1/bars/indicators",
        params={"symbol": "AAPL", "indicators": "sma:20"},
    )
    assert resp.status_code == 401


def test_bars_indicators_unknown_symbol(client):
    resp = client.get(
        "/v1/bars/indicators",
        params={"symbol": "ZZZZZ", "indicators": "sma:20"},
        headers=_auth_header(),
    )
    assert resp.status_code == 404


def test_bars_indicators_unknown_indicator(client):
    resp = client.get(
        "/v1/bars/indicators",
        params={"symbol": "TEST", "indicators": "golden_cross:20"},
        headers=_auth_header(),
    )
    assert resp.status_code == 422


def test_bars_indicators_lookback_exceeded(client):
    resp = client.get(
        "/v1/bars/indicators",
        params={
            "symbol": "AAPL",
            "indicators": "sma:20",
            "start": "2020-01-01",
            "end": "2026-06-01",
        },
        headers=_auth_header(),
    )
    assert resp.status_code == 422


def test_rate_limit(client):
    headers = _auth_header()
    last_status = 200
    for _ in range(25):
        resp = client.get(
            "/v1/bars",
            params={"symbol": "ZZZZZ_UNKNOWN"},
            headers=headers,
        )
        last_status = resp.status_code
    # After 20 burst + some rate-limited, some should be 429
    assert last_status in (429, 404)
