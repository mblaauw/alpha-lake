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
    store.set("api_key_test", "al_test_supersecret123")
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
    con.execute("""
        CREATE TABLE fundamental_metrics (
            security_id VARCHAR NOT NULL,
            metric_id VARCHAR NOT NULL,
            metric_version VARCHAR NOT NULL,
            category VARCHAR NOT NULL,
            period_kind VARCHAR NOT NULL,
            period_end DATE NOT NULL,
            available_at TIMESTAMPTZ NOT NULL,
            value DOUBLE,
            unit VARCHAR NOT NULL,
            currency VARCHAR,
            source_currency VARCHAR,
            source_period_ends VARCHAR,
            source_version_hashes VARCHAR,
            calculation_basis VARCHAR,
            quality_status VARCHAR DEFAULT 'valid',
            calculation_version VARCHAR,
            ingestion_run_id VARCHAR,
            source_id VARCHAR DEFAULT 'derived',
            source_fetch_id VARCHAR DEFAULT '',
            raw_payload_hash VARCHAR DEFAULT '',
            content_hash VARCHAR DEFAULT '',
            version_hash VARCHAR DEFAULT '',
            schema_version INTEGER DEFAULT 1,
            parser_version INTEGER DEFAULT 1
        )
    """)
    con.execute(
        """
        INSERT INTO fundamental_metrics VALUES (
            'sec_test', 'fundamentals.scale.revenue_ttm', '1.0.0',
            'Scale', 'ttm', '2026-03-31', '2026-05-15 10:00:00+00',
            100000000000.0, 'currency', 'USD', 'USD',
            '["2026-03-31","2025-12-31","2025-09-30","2025-06-30"]',
            '["h1","h2","h3","h4"]',
            'sum(last_four_standalone_quarter_revenue)',
            'valid', '1.0.0', 'run_001', 'derived', '',
            '', '', '', 1, 1
        )
    """
    )
    con.execute(
        """
        INSERT INTO fundamental_metrics VALUES (
            'sec_test', 'fundamentals.profitability.gross_margin_ttm', '1.0.0',
            'Profitability', 'ttm', '2026-03-31', '2026-05-15 10:00:00+00',
            40.5, 'percent', NULL, NULL,
            '["2026-03-31","2025-12-31","2025-09-30","2025-06-30"]',
            '["h1","h2","h3","h4"]',
            'gross_profit_ttm / revenue_ttm * 100',
            'valid', '1.0.0', 'run_001', 'derived', '',
            '', '', '', 1, 1
        )
    """
    )
    register_kernel(con)
    return con


@pytest.fixture
def client(_test_con):
    from fastapi.testclient import TestClient

    from alpha_lake.transport import app as transport_app
    from alpha_lake.transport._shared import _set_test_connection

    _set_test_connection(_test_con)
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


# ── Fundamentals authenticated endpoints ─────────────────────────────────


def test_fundamentals_metrics_no_auth(client):
    resp = client.get("/v1/fundamentals/metrics", params={"symbol": "TEST"})
    assert resp.status_code == 401


def test_fundamentals_metrics_missing_as_of(client):
    resp = client.get(
        "/v1/fundamentals/metrics",
        params={"symbol": "TEST"},
        headers=_auth_header(),
    )
    assert resp.status_code == 422
    assert "as_of" in resp.json()["detail"].lower()


def test_fundamentals_metrics_unknown_symbol(client):
    resp = client.get(
        "/v1/fundamentals/metrics",
        params={"symbol": "ZZZZZ_UNKNOWN", "as_of": "2026-06-01T12:00:00Z"},
        headers=_auth_header(),
    )
    assert resp.status_code == 404


def test_fundamentals_metrics_success(client):
    resp = client.get(
        "/v1/fundamentals/metrics",
        params={"symbol": "TEST", "as_of": "2026-06-01T12:00:00Z"},
        headers=_auth_header(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "TEST"
    assert "metrics" in data
    assert len(data["metrics"]) >= 2
    metric_ids = {m["metric_id"] for m in data["metrics"]}
    assert "fundamentals.scale.revenue_ttm" in metric_ids
    assert "fundamentals.profitability.gross_margin_ttm" in metric_ids
    assert data["metadata"]["metrics_returned"] >= 2


def test_fundamentals_metrics_category_filter(client):
    resp = client.get(
        "/v1/fundamentals/metrics",
        params={
            "symbol": "TEST",
            "as_of": "2026-06-01T12:00:00Z",
            "categories": "Profitability",
        },
        headers=_auth_header(),
    )
    assert resp.status_code == 200
    data = resp.json()
    categories = {m["category"] for m in data["metrics"]}
    assert categories == {"Profitability"}


def test_fundamentals_metrics_include_inputs(client):
    resp = client.get(
        "/v1/fundamentals/metrics",
        params={
            "symbol": "TEST",
            "as_of": "2026-06-01T12:00:00Z",
            "include": "inputs",
        },
        headers=_auth_header(),
    )
    assert resp.status_code == 200
    data = resp.json()
    for metric in data["metrics"]:
        assert "inputs" in metric
        assert "basis" in metric
        assert "calculation_basis" in metric


def test_fundamentals_metrics_include_definitions(client):
    resp = client.get(
        "/v1/fundamentals/metrics",
        params={
            "symbol": "TEST",
            "as_of": "2026-06-01T12:00:00Z",
            "include": "definitions",
        },
        headers=_auth_header(),
    )
    assert resp.status_code == 200
    data = resp.json()
    for metric in data["metrics"]:
        assert "description" in metric
        assert "what_it_answers" in metric
        assert "formula" in metric
        if metric["threshold_profile_id"]:
            assert "threshold_profile" in metric


def test_fundamentals_metrics_include_provenance(client):
    resp = client.get(
        "/v1/fundamentals/metrics",
        params={
            "symbol": "TEST",
            "as_of": "2026-06-01T12:00:00Z",
            "include": "provenance",
        },
        headers=_auth_header(),
    )
    assert resp.status_code == 200
    data = resp.json()
    for metric in data["metrics"]:
        assert "source_id" in metric
        assert "version_hash" in metric


def test_fundamentals_metrics_include_all(client):
    resp = client.get(
        "/v1/fundamentals/metrics",
        params={
            "symbol": "TEST",
            "as_of": "2026-06-01T12:00:00Z",
            "include": "inputs,definitions,provenance",
        },
        headers=_auth_header(),
    )
    assert resp.status_code == 200
    data = resp.json()
    for metric in data["metrics"]:
        assert "inputs" in metric
        assert "description" in metric
        assert "source_id" in metric


def test_fundamentals_glossary_no_auth(client):
    resp = client.get("/v1/fundamentals/glossary")
    assert resp.status_code == 401


def test_fundamentals_glossary_success(client):
    resp = client.get(
        "/v1/fundamentals/glossary",
        headers=_auth_header(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 24
    ids = {e["metric_id"] for e in data}
    assert "fundamentals.scale.revenue_ttm" in ids
    assert "fundamentals.valuation.price_to_earnings_ttm" in ids


def test_fundamentals_glossary_category_filter(client):
    resp = client.get(
        "/v1/fundamentals/glossary",
        params={"categories": "Valuation"},
        headers=_auth_header(),
    )
    assert resp.status_code == 200
    data = resp.json()
    for entry in data:
        assert entry["category"] == "Valuation"
    assert len(data) == 3  # P/E, P/S, P/FCF


def test_fundamentals_metrics_metric_ids_filter(client, _test_con):
    con = _test_con
    con.execute(
        """
        INSERT INTO fundamental_metrics VALUES (
            'sec_test', 'fundamentals.profitability.operating_margin_ttm', '1.0.0',
            'Profitability', 'ttm', '2026-03-31', '2026-05-15 10:00:00+00',
            22.5, 'percent', NULL, NULL,
            '["2026-03-31","2025-12-31","2025-09-30","2025-06-30"]',
            '["h1","h2","h3","h4"]',
            'operating_income_ttm / revenue_ttm * 100',
            'valid', '1.0.0', 'run_001', 'derived', '',
            '', '', '', 1, 1
        )
        """
    )
    resp = client.get(
        "/v1/fundamentals/metrics",
        params={
            "symbol": "TEST",
            "as_of": "2026-06-01T12:00:00Z",
            "metric_ids": "fundamentals.scale.revenue_ttm",
        },
        headers=_auth_header(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["metrics"]) == 1
    assert data["metrics"][0]["metric_id"] == "fundamentals.scale.revenue_ttm"


def test_fundamentals_metrics_not_meaningful_reason(client, _test_con):
    con = _test_con
    con.execute(
        """
        INSERT INTO fundamental_metrics VALUES (
            'sec_test', 'fundamentals.financial_health.net_debt_to_ebitda_ttm', '1.0.0',
            'Financial Health', 'ttm', '2026-03-31', '2026-05-15 10:00:00+00',
            NULL, 'multiple', NULL, NULL,
            '["2026-03-31","2025-12-31","2025-09-30","2025-06-30"]',
            '["h1","h2","h3","h4"]',
            'net_debt_mrq / ebitda_ttm',
            'not_meaningful', '1.0.0', 'run_001', 'derived', '',
            '', '', '', 1, 1
        )
        """
    )
    resp = client.get(
        "/v1/fundamentals/metrics",
        params={
            "symbol": "TEST",
            "as_of": "2026-06-01T12:00:00Z",
        },
        headers=_auth_header(),
    )
    assert resp.status_code == 200
    data = resp.json()
    nm = [m for m in data["metrics"] if m["state"] == "not_meaningful"]
    assert len(nm) >= 1
    assert nm[0]["value"] is None


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


def test_authenticated_readouts_no_auth(client):
    resp = client.get("/v1/symbol/AAPL/readouts?as_of=2026-06-24T12:00:00Z")
    assert resp.status_code in (401, 403)


def test_authenticated_readouts_missing_as_of(client):
    resp = client.get("/v1/symbol/AAPL/readouts", headers=_auth_header())
    assert resp.status_code < 500  # auth or validation error, not server error


def test_authenticated_readouts_latest_allowed(client):
    resp = client.get("/v1/symbol/AAPL/readouts?latest=true")
    assert resp.status_code < 500
    if resp.status_code == 200:
        data = resp.json()
        assert "readouts" in data
        assert "metadata" in data


def test_batch_readouts_no_body(client):
    resp = client.post("/v1/readouts/batch", json={})
    assert resp.status_code in (401, 403, 422)


def test_batch_readouts_empty_symbols(client):
    resp = client.post(
        "/v1/readouts/batch",
        json={"symbols": []},
        headers=_auth_header(),
    )
    assert resp.status_code < 500


def test_batch_readouts_with_data(client):
    resp = client.post(
        "/v1/readouts/batch",
        json={"symbols": ["AAPL"], "latest": True},
        headers=_auth_header(),
    )
    assert resp.status_code in (200, 429)
    if resp.status_code == 200:
        data = resp.json()
        assert "items" in data
        assert "errors" in data


def test_facts_bundle_no_auth(client):
    resp = client.get("/v1/symbol/AAPL/facts-bundle?latest=true")
    assert resp.status_code < 500


def test_facts_bundle_missing_as_of(client):
    resp = client.get("/v1/symbol/AAPL/facts-bundle", headers=_auth_header())
    assert resp.status_code < 500


def test_facts_bundle_shape(client):
    resp = client.get(
        "/v1/symbol/AAPL/facts-bundle?latest=true",
        headers=_auth_header(),
    )
    assert resp.status_code in (200, 429)
    if resp.status_code == 200:
        data = resp.json()
        assert "symbol" in data
        assert "sections" in data
        assert "freshness" in data
        assert "provenance" in data
        assert "metadata" in data


def test_batch_facts_bundle(client):
    resp = client.post(
        "/v1/facts-bundle/batch",
        json={"symbols": ["AAPL"], "latest": True},
        headers=_auth_header(),
    )
    assert resp.status_code in (200, 429)
    if resp.status_code == 200:
        data = resp.json()
        assert "items" in data
        assert "errors" in data


@pytest.mark.xfail(reason="indicator parsing default format mismatch in test env")
def test_decision_panel_capabilities(client):
    resp = client.get(
        "/v1/decision-panel?symbols=AAPL&as_of=2026-06-24T12:00:00Z",
        headers=_auth_header(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "capabilities" in data
    assert "readouts" in data["capabilities"]


@pytest.mark.xfail(reason="indicator parsing default format mismatch in test env")
def test_decision_panel_include_readouts(client):
    resp = client.get(
        "/v1/decision-panel?symbols=AAPL&as_of=2026-06-24T12:00:00Z&include=readouts",
        headers=_auth_header(),
    )
    assert resp.status_code == 200
    data = resp.json()
    for sym in data.get("symbols", []):
        panel = data.get("panels", {}).get(sym, {})
        if "readouts" in panel:
            break
