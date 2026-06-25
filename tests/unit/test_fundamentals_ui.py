from __future__ import annotations

from pathlib import Path

_APP_JS = Path("src/alpha_lake/transport/static/app.js")
_INDEX_HTML = Path("src/alpha_lake/transport/static/index.html")


def test_fundamentals_nav_tab_exists():
    html = _INDEX_HTML.read_text()
    assert 'data-tab="fundamentals"' in html
    assert "Fundamentals" in html


def test_render_fundamentals_function_exists():
    js = _APP_JS.read_text()
    assert "function renderFundamentals(c)" in js or "renderFundamentals" in js


def test_fundamentals_glossary_fetch_exists():
    js = _APP_JS.read_text()
    assert "fetchFundGlossary" in js


def test_no_threshold_calculation_in_frontend():
    js = _APP_JS.read_text()
    lines = js.split("\n")
    threshold_assignments = [
        line_.strip() for line_ in lines if "threshold_state" in line_ and "=" in line_
    ]
    for line in threshold_assignments:
        assert (
            "m." in line
            or "row." in line
            or "data." in line
            or ".threshold_state" not in line.split("=")[1]
        ), f"potential threshold calculation in frontend: {line}"


def test_fundamentals_pins_key_is_independent():
    js = _APP_JS.read_text()
    assert "lw_fund_pins" in js
    assert "setFundPins" in js


def test_fundamentals_overview_metrics_defined():
    js = _APP_JS.read_text()
    assert "_fundOverviewIds" in js


def test_fundamentals_api_endpoint_called():
    js = _APP_JS.read_text()
    assert "symbol/" in js and "fundamentals" in js
