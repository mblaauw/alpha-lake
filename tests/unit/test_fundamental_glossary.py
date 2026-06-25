from __future__ import annotations

import json

from alpha_lake.interpretation.fundamentals_glossary import (
    FUNDAMENTAL_GLOSSARY,
    FUNDAMENTALS_OVERVIEW,
    get_glossary_entry,
    get_metric_threshold_profile_id,
    get_threshold_profile,
    glossary_to_json,
    resolve_fundamental_state,
)

_MATERIALIZED_METRIC_IDS = [
    "fundamentals.scale.revenue_ttm",
    "fundamentals.scale.ebitda_ttm",
    "fundamentals.profitability.gross_margin_ttm",
    "fundamentals.profitability.operating_margin_ttm",
    "fundamentals.profitability.ebitda_margin_ttm",
    "fundamentals.profitability.net_margin_ttm",
    "fundamentals.cash_flow_quality.cfo_to_net_income_ttm",
    "fundamentals.cash_flow_quality.fcf_conversion_ttm",
    "fundamentals.profitability.fcf_margin_ttm",
    "fundamentals.growth.revenue_yoy_ttm",
    "fundamentals.growth.eps_diluted_yoy_ttm",
    "fundamentals.growth.ebitda_yoy_ttm",
    "fundamentals.financial_health.cash_and_equivalents_mrq",
    "fundamentals.financial_health.total_debt_mrq",
    "fundamentals.financial_health.net_debt_mrq",
    "fundamentals.financial_health.net_debt_to_ebitda_ttm",
    "fundamentals.financial_health.current_ratio_mrq",
    "fundamentals.financial_health.debt_to_equity_mrq",
]

_READ_TIME_METRIC_IDS = [
    "fundamentals.valuation.price_to_earnings_ttm",
    "fundamentals.valuation.price_to_sales_ttm",
    "fundamentals.valuation.price_to_fcf_ttm",
]

_NOT_MATERIALIZED_IDS = [
    "fundamentals.profitability.diluted_eps_ttm",
    "fundamentals.scale.revenue_per_share_ttm",
    "fundamentals.cash_flow_quality.fcf_per_share_ttm",
]

_ALL_METRIC_IDS = _MATERIALIZED_METRIC_IDS + _READ_TIME_METRIC_IDS + _NOT_MATERIALIZED_IDS

_ALL_PROFILE_IDS = [
    "context_only_v1",
    "relative_valuation_multiple_v1",
    "yield_v1",
    "profitability_peer_percentile_v1",
    "roic_absolute_v1",
    "growth_yoy_v1",
    "margin_change_v1",
    "leverage_v1",
    "debt_to_equity_v1",
    "liquidity_v1",
    "interest_coverage_v1",
    "cash_conversion_v1",
    "share_count_change_v1",
    "payout_ratio_v1",
    "estimate_revision_v1",
]


def test_registry_completeness_covers_every_metric_id():
    for metric_id in _ALL_METRIC_IDS:
        entry = get_glossary_entry(metric_id)
        assert entry is not None, f"missing glossary entry for {metric_id}"
        assert entry.metric_id == metric_id
        assert entry.name
        assert entry.full_name
        assert entry.category
        assert entry.description
        assert entry.what_it_answers
        assert entry.formula
        assert entry.inputs
        assert entry.basis
        assert entry.unit
        assert entry.display_formatter
        assert entry.threshold_profile_id
        assert entry.surfaces
        assert isinstance(entry.implemented, bool)


def test_materialized_metrics_are_flagged_implemented():
    for metric_id in _MATERIALIZED_METRIC_IDS + _READ_TIME_METRIC_IDS:
        entry = get_glossary_entry(metric_id)
        assert entry is not None
        assert entry.implemented is True, f"{metric_id} should be implemented=True"


def test_not_materialized_metrics_are_flagged_not_implemented():
    for metric_id in _NOT_MATERIALIZED_IDS:
        entry = get_glossary_entry(metric_id)
        assert entry is not None
        assert entry.implemented is False, f"{metric_id} should be implemented=False"


def test_every_entry_references_a_valid_threshold_profile():
    for metric_id, entry in FUNDAMENTAL_GLOSSARY.items():
        profile = get_threshold_profile(entry.threshold_profile_id)
        assert profile is not None, (
            f"{metric_id} references unknown profile {entry.threshold_profile_id}"
        )


def test_all_requested_profiles_are_defined_and_versioned():
    for pid in _ALL_PROFILE_IDS:
        profile = get_threshold_profile(pid)
        assert profile is not None, f"missing threshold profile {pid}"
        assert profile.profile_id == pid
        assert profile.version
        assert profile.method in ("discrete", "context", "peer_percentile")


def test_context_only_always_returns_gray_contextual_state():
    profile = get_threshold_profile("context_only_v1")
    assert profile is not None
    for value in [0.0, 100.0, -50.0, 1_000_000.0]:
        state, tone, label = resolve_fundamental_state(profile, value)
        assert state == "contextual"
        assert tone == "gray"
        assert label == "contextual"


def test_context_only_returns_unavailable_for_none():
    profile = get_threshold_profile("context_only_v1")
    assert profile is not None
    state, tone, label = resolve_fundamental_state(profile, None)
    assert state == "unavailable"
    assert tone == "gray"


def test_discrete_leverage_boundary_exact_cutoffs():
    profile = get_threshold_profile("leverage_v1")
    assert profile is not None

    state, tone, _ = resolve_fundamental_state(profile, 1.5)
    assert state == "low"
    assert tone == "gray"

    state, tone, _ = resolve_fundamental_state(profile, 2.0)
    assert state == "median_range"
    assert tone == "amber"

    state, tone, _ = resolve_fundamental_state(profile, 3.99)
    assert state == "median_range"

    state, tone, _ = resolve_fundamental_state(profile, 4.0)
    assert state == "high"
    assert tone == "red"


def test_discrete_liquidity_boundary_exact_cutoffs():
    profile = get_threshold_profile("liquidity_v1")
    assert profile is not None

    state, tone, _ = resolve_fundamental_state(profile, 0.5)
    assert state == "low"
    assert tone == "red"

    state, tone, _ = resolve_fundamental_state(profile, 1.0)
    assert state == "median_range"

    state, tone, _ = resolve_fundamental_state(profile, 2.0)
    assert state == "high"
    assert tone == "gray"


def test_discrete_growth_boundary_exact_cutoffs():
    profile = get_threshold_profile("growth_yoy_v1")
    assert profile is not None

    state, tone, _ = resolve_fundamental_state(profile, -2.0)
    assert state == "contracting"
    assert tone == "red"

    state, tone, _ = resolve_fundamental_state(profile, -1.0)
    assert state == "stable"

    state, tone, _ = resolve_fundamental_state(profile, 0.0)
    assert state == "stable"

    state, tone, _ = resolve_fundamental_state(profile, 1.0)
    assert state == "expanding"
    assert tone == "green"


def test_discrete_valuation_boundary_exact_cutoffs():
    profile = get_threshold_profile("relative_valuation_multiple_v1")
    assert profile is not None

    state, tone, _ = resolve_fundamental_state(profile, 10.0)
    assert state == "low"
    assert tone == "gray"

    state, tone, _ = resolve_fundamental_state(profile, 15.0)
    assert state == "median_range"

    state, tone, _ = resolve_fundamental_state(profile, 30.0)
    assert state == "high"
    assert tone == "amber"


def test_discrete_none_returns_unavailable():
    profile = get_threshold_profile("leverage_v1")
    assert profile is not None
    state, tone, label = resolve_fundamental_state(profile, None)
    assert state == "unavailable"
    assert tone == "gray"
    assert label == "unavailable"


def test_peer_percentile_returns_gray_raw_value_without_baseline():
    profile = get_threshold_profile("profitability_peer_percentile_v1")
    assert profile is not None
    assert profile.method == "peer_percentile"
    assert profile.min_peer_count > 0

    state, tone, label = resolve_fundamental_state(profile, 40.0)
    assert state == "raw_value"
    assert tone == "gray"
    assert "peer data insufficient" in label


def test_peer_percentile_returns_gray_raw_value_with_insufficient_peers():
    profile = get_threshold_profile("profitability_peer_percentile_v1")
    assert profile is not None

    state, tone, _ = resolve_fundamental_state(profile, 40.0, has_peer_baseline=True, peer_count=2)
    assert state == "raw_value"
    assert tone == "gray"


def test_peer_percentile_returns_raw_value_with_sufficient_peers_but_not_implemented():
    profile = get_threshold_profile("profitability_peer_percentile_v1")
    assert profile is not None

    state, tone, _ = resolve_fundamental_state(profile, 40.0, has_peer_baseline=True, peer_count=10)
    assert state == "raw_value"
    assert tone == "gray"


def test_peer_percentile_none_returns_unavailable():
    profile = get_threshold_profile("profitability_peer_percentile_v1")
    assert profile is not None

    state, _, _ = resolve_fundamental_state(profile, None, has_peer_baseline=True, peer_count=10)
    assert state == "unavailable"


def test_glossary_to_json_is_json_safe():
    payloads = glossary_to_json()
    assert len(payloads) == len(FUNDAMENTAL_GLOSSARY)

    serialized = json.dumps(payloads)
    round_tripped = json.loads(serialized)
    assert len(round_tripped) == len(FUNDAMENTAL_GLOSSARY)

    for payload in round_tripped:
        assert "metric_id" in payload
        assert "name" in payload
        assert "threshold_profile" in payload
        tp = payload["threshold_profile"]
        if tp is not None:
            assert "profile_id" in tp
            assert "bands" in tp
            assert isinstance(tp["bands"], list)


def test_glossary_to_json_includes_threshold_profile_metadata():
    payloads = glossary_to_json()
    pe_entry = next(
        p for p in payloads if p["metric_id"] == "fundamentals.valuation.price_to_earnings_ttm"
    )
    assert pe_entry["threshold_profile"] is not None
    assert pe_entry["threshold_profile"]["profile_id"] == "relative_valuation_multiple_v1"
    assert len(pe_entry["threshold_profile"]["bands"]) == 3


def test_get_metric_threshold_profile_id_returns_expected():
    assert get_metric_threshold_profile_id("fundamentals.growth.revenue_yoy_ttm") == "growth_yoy_v1"
    assert (
        get_metric_threshold_profile_id("fundamentals.financial_health.net_debt_to_ebitda_ttm")
        == "leverage_v1"
    )
    assert get_metric_threshold_profile_id("nonexistent.metric") == ""


def test_overview_ids_all_exist_in_glossary():
    for mid in FUNDAMENTALS_OVERVIEW:
        entry = get_glossary_entry(mid)
        assert entry is not None, f"overview ID {mid} missing from glossary"
        assert entry.implemented, f"overview ID {mid} has implemented=False"


def test_every_overview_id_has_a_dashboard_category():
    known = {
        "Scale",
        "Valuation",
        "Profitability",
        "Growth",
        "Financial Health",
        "Cash Flow Quality",
        "Cash Flow",
        "Capital Allocation",
        "Estimates",
        "Events",
    }
    for mid in FUNDAMENTALS_OVERVIEW:
        entry = get_glossary_entry(mid)
        assert entry is not None
        assert entry.category in known, f"{mid} has unknown category {entry.category}"


def test_no_recommendation_semantics_in_glossary_text():
    forbidden = {"signal", "bullish", "bearish", "buy", "sell", "golden_cross", "hype", "candidate"}
    for metric_id, entry in FUNDAMENTAL_GLOSSARY.items():
        if entry.category in ("Estimates", "Events"):
            continue
        text = " ".join(
            [entry.name, entry.full_name, entry.description, entry.what_it_answers, entry.formula]
        ).lower()
        for word in forbidden:
            assert word not in text, f"forbidden word '{word}' in {metric_id}: {text}"
