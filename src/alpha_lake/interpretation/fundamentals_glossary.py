from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class FundamentalBand:
    state: str
    tone: str
    label: str
    min_value: float | None = None
    max_value: float | None = None


@dataclass(frozen=True)
class FundamentalThresholdProfile:
    profile_id: str
    version: str
    method: Literal["discrete", "context", "peer_percentile"]
    description: str
    min_peer_count: int = 0
    bands: tuple[FundamentalBand, ...] = ()


@dataclass(frozen=True)
class FundamentalGlossaryEntry:
    metric_id: str
    name: str
    full_name: str
    category: str
    description: str
    what_it_answers: str
    formula: str
    inputs: tuple[str, ...]
    basis: str
    unit: str
    display_formatter: str
    threshold_profile_id: str
    surfaces: tuple[str, ...]
    implemented: bool
    unavailable_conditions: tuple[str, ...] = ()


TONE_GRAY = "gray"
TONE_GREEN = "green"
TONE_RED = "red"
TONE_AMBER = "amber"

CONTEXTUAL = FundamentalBand("contextual", TONE_GRAY, "contextual")

# ── Threshold profiles ─────────────────────────────────────────────────────

FUNDAMENTAL_THRESHOLDS: dict[str, FundamentalThresholdProfile] = {
    "context_only_v1": FundamentalThresholdProfile(
        "context_only_v1",
        "1.0.0",
        "context",
        "Contextual measurement; no directional classification.",
        bands=(CONTEXTUAL,),
    ),
    "relative_valuation_multiple_v1": FundamentalThresholdProfile(
        "relative_valuation_multiple_v1",
        "1.0.0",
        "discrete",
        "Absolute bands for price-relative multiples (P/E, P/S, P/FCF).",
        bands=(
            FundamentalBand("low", TONE_GRAY, "low", min_value=0.0, max_value=15.0),
            FundamentalBand(
                "median_range", TONE_GRAY, "median range", min_value=15.0, max_value=30.0
            ),
            FundamentalBand("high", TONE_AMBER, "high", min_value=30.0),
        ),
    ),
    "yield_v1": FundamentalThresholdProfile(
        "yield_v1",
        "1.0.0",
        "discrete",
        "Absolute bands for yield metrics (values in percentage points).",
        bands=(
            FundamentalBand("low", TONE_GRAY, "low", max_value=2.0),
            FundamentalBand(
                "median_range", TONE_GRAY, "median range", min_value=2.0, max_value=6.0
            ),
            FundamentalBand("high", TONE_GRAY, "high", min_value=6.0),
        ),
    ),
    "profitability_peer_percentile_v1": FundamentalThresholdProfile(
        "profitability_peer_percentile_v1",
        "1.0.0",
        "peer_percentile",
        "Profitability margins classified against a peer baseline; requires sufficient peers.",
        min_peer_count=5,
        bands=(
            FundamentalBand("below_median", TONE_GRAY, "below median"),
            FundamentalBand("median_range", TONE_GRAY, "median range"),
            FundamentalBand("above_median", TONE_GRAY, "above median"),
        ),
    ),
    "roic_absolute_v1": FundamentalThresholdProfile(
        "roic_absolute_v1",
        "1.0.0",
        "discrete",
        "Return on invested capital absolute bands (values in percentage points).",
        bands=(
            FundamentalBand("low", TONE_AMBER, "low", max_value=8.0),
            FundamentalBand(
                "median_range", TONE_GRAY, "median range", min_value=8.0, max_value=15.0
            ),
            FundamentalBand("high", TONE_GRAY, "high", min_value=15.0),
        ),
    ),
    "growth_yoy_v1": FundamentalThresholdProfile(
        "growth_yoy_v1",
        "1.0.0",
        "discrete",
        "Year-over-year growth direction bands (values in percentage points).",
        bands=(
            FundamentalBand("contracting", TONE_RED, "contracting", max_value=-1.0),
            FundamentalBand("stable", TONE_GRAY, "stable", min_value=-1.0, max_value=1.0),
            FundamentalBand("expanding", TONE_GREEN, "expanding", min_value=1.0),
        ),
    ),
    "margin_change_v1": FundamentalThresholdProfile(
        "margin_change_v1",
        "1.0.0",
        "discrete",
        "Period-over-period margin change direction (values in percentage points).",
        bands=(
            FundamentalBand("declining", TONE_RED, "declining", max_value=-1.0),
            FundamentalBand("stable", TONE_GRAY, "stable", min_value=-1.0, max_value=1.0),
            FundamentalBand("expanding", TONE_GRAY, "expanding", min_value=1.0),
        ),
    ),
    "leverage_v1": FundamentalThresholdProfile(
        "leverage_v1",
        "1.0.0",
        "discrete",
        "Net-debt-to-EBITDA leverage bands.",
        bands=(
            FundamentalBand("low", TONE_GRAY, "low", max_value=2.0),
            FundamentalBand(
                "median_range", TONE_AMBER, "median range", min_value=2.0, max_value=4.0
            ),
            FundamentalBand("high", TONE_RED, "high", min_value=4.0),
        ),
    ),
    "debt_to_equity_v1": FundamentalThresholdProfile(
        "debt_to_equity_v1",
        "1.0.0",
        "discrete",
        "Debt-to-equity ratio bands.",
        bands=(
            FundamentalBand("low", TONE_GRAY, "low", max_value=0.5),
            FundamentalBand(
                "median_range", TONE_AMBER, "median range", min_value=0.5, max_value=2.0
            ),
            FundamentalBand("high", TONE_RED, "high", min_value=2.0),
        ),
    ),
    "liquidity_v1": FundamentalThresholdProfile(
        "liquidity_v1",
        "1.0.0",
        "discrete",
        "Current-ratio liquidity bands.",
        bands=(
            FundamentalBand("low", TONE_RED, "low", max_value=1.0),
            FundamentalBand(
                "median_range", TONE_AMBER, "median range", min_value=1.0, max_value=2.0
            ),
            FundamentalBand("high", TONE_GRAY, "high", min_value=2.0),
        ),
    ),
    "interest_coverage_v1": FundamentalThresholdProfile(
        "interest_coverage_v1",
        "1.0.0",
        "discrete",
        "EBIT-to-interest-expense coverage bands.",
        bands=(
            FundamentalBand("low", TONE_RED, "low", max_value=2.0),
            FundamentalBand(
                "median_range", TONE_AMBER, "median range", min_value=2.0, max_value=5.0
            ),
            FundamentalBand("high", TONE_GRAY, "high", min_value=5.0),
        ),
    ),
    "cash_conversion_v1": FundamentalThresholdProfile(
        "cash_conversion_v1",
        "1.0.0",
        "discrete",
        "Free-cash-flow-to-net-income conversion ratio bands.",
        bands=(
            FundamentalBand("low", TONE_AMBER, "low", max_value=0.5),
            FundamentalBand(
                "median_range", TONE_GRAY, "median range", min_value=0.5, max_value=1.0
            ),
            FundamentalBand("high", TONE_GRAY, "high", min_value=1.0),
        ),
    ),
    "share_count_change_v1": FundamentalThresholdProfile(
        "share_count_change_v1",
        "1.0.0",
        "discrete",
        "Period-over-period diluted share count change (values in percentage points).",
        bands=(
            FundamentalBand("diluting", TONE_AMBER, "diluting", max_value=-1.0),
            FundamentalBand("stable", TONE_GRAY, "stable", min_value=-1.0, max_value=1.0),
            FundamentalBand("reducing", TONE_GRAY, "reducing", min_value=1.0),
        ),
    ),
    "payout_ratio_v1": FundamentalThresholdProfile(
        "payout_ratio_v1",
        "1.0.0",
        "discrete",
        "Dividend payout ratio bands.",
        bands=(
            FundamentalBand("low", TONE_GRAY, "low", max_value=0.2),
            FundamentalBand(
                "median_range", TONE_GRAY, "median range", min_value=0.2, max_value=0.6
            ),
            FundamentalBand("high", TONE_AMBER, "high", min_value=0.6),
        ),
    ),
    "estimate_revision_v1": FundamentalThresholdProfile(
        "estimate_revision_v1",
        "1.0.0",
        "discrete",
        "Analyst estimate revision direction.",
        bands=(
            FundamentalBand("downward", TONE_RED, "downward", max_value=-0.01),
            FundamentalBand("stable", TONE_GRAY, "stable", min_value=-0.01, max_value=0.01),
            FundamentalBand("upward", TONE_GRAY, "upward", min_value=0.01),
        ),
    ),
    "proximity_v1": FundamentalThresholdProfile(
        "proximity_v1",
        "1.0.0",
        "discrete",
        "Time proximity bands (lower = closer to event).",
        bands=(
            FundamentalBand("imminent", TONE_AMBER, "imminent", max_value=3.0),
            FundamentalBand("near", TONE_GRAY, "near", min_value=3.0, max_value=14.0),
            FundamentalBand("distant", TONE_GRAY, "distant", min_value=14.0),
        ),
    ),
}

# ── Glossary entries ──────────────────────────────────────────────────────

FUNDAMENTAL_GLOSSARY: dict[str, FundamentalGlossaryEntry] = {
    # ── Scale (contextual) ─────────────────────────────────────────────────
    "fundamentals.scale.revenue_ttm": FundamentalGlossaryEntry(
        "fundamentals.scale.revenue_ttm",
        "Revenue (TTM)",
        "Trailing-twelve-month revenue",
        "Scale",
        "Total revenue over the last four standalone quarters.",
        "What is the revenue scale of this business?",
        "sum(last_four_standalone_quarter_revenue)",
        ("revenue",),
        "ttm",
        "currency",
        "currency_2dp",
        "context_only_v1",
        ("card", "detail"),
        True,
        ("insufficient_quarter_history",),
    ),
    "fundamentals.scale.ebitda_ttm": FundamentalGlossaryEntry(
        "fundamentals.scale.ebitda_ttm",
        "EBITDA (TTM)",
        "Trailing-twelve-month EBITDA",
        "Scale",
        "Earnings before interest, taxes, depreciation, and amortization over TTM.",
        "What is the operating cash earnings scale?",
        "sum(last_four_standalone_quarter_ebitda)",
        ("ebitda",),
        "ttm",
        "currency",
        "currency_2dp",
        "context_only_v1",
        ("card", "detail"),
        True,
        ("insufficient_quarter_history",),
    ),
    # ── Profitability ──────────────────────────────────────────────────────
    "fundamentals.profitability.gross_margin_ttm": FundamentalGlossaryEntry(
        "fundamentals.profitability.gross_margin_ttm",
        "Gross Margin (TTM)",
        "TTM gross profit margin",
        "Profitability",
        "Gross profit as a percentage of revenue over TTM.",
        "How much revenue remains after cost of goods sold?",
        "gross_profit_ttm / revenue_ttm * 100",
        ("gross_profit", "revenue"),
        "ttm",
        "percent",
        "percent_2dp",
        "profitability_peer_percentile_v1",
        ("card", "detail"),
        True,
        ("insufficient_quarter_history", "non_positive_revenue"),
    ),
    "fundamentals.profitability.operating_margin_ttm": FundamentalGlossaryEntry(
        "fundamentals.profitability.operating_margin_ttm",
        "Operating Margin (TTM)",
        "TTM operating income margin",
        "Profitability",
        "Operating income as a percentage of revenue over TTM.",
        "How much revenue remains after operating expenses?",
        "operating_income_ttm / revenue_ttm * 100",
        ("operating_income", "revenue"),
        "ttm",
        "percent",
        "percent_2dp",
        "profitability_peer_percentile_v1",
        ("card", "detail"),
        True,
        ("insufficient_quarter_history", "non_positive_revenue"),
    ),
    "fundamentals.profitability.ebitda_margin_ttm": FundamentalGlossaryEntry(
        "fundamentals.profitability.ebitda_margin_ttm",
        "EBITDA Margin (TTM)",
        "TTM EBITDA margin",
        "Profitability",
        "EBITDA as a percentage of revenue over TTM.",
        "What is the operating cash earnings efficiency?",
        "ebitda_ttm / revenue_ttm * 100",
        ("ebitda", "revenue"),
        "ttm",
        "percent",
        "percent_2dp",
        "profitability_peer_percentile_v1",
        ("card", "detail"),
        True,
        ("insufficient_quarter_history", "non_positive_revenue"),
    ),
    "fundamentals.profitability.net_margin_ttm": FundamentalGlossaryEntry(
        "fundamentals.profitability.net_margin_ttm",
        "Net Margin (TTM)",
        "TTM net income margin",
        "Profitability",
        "Net income as a percentage of revenue over TTM.",
        "How much revenue remains after all expenses?",
        "net_income_ttm / revenue_ttm * 100",
        ("net_income", "revenue"),
        "ttm",
        "percent",
        "percent_2dp",
        "profitability_peer_percentile_v1",
        ("card", "detail"),
        True,
        ("insufficient_quarter_history", "non_positive_revenue"),
    ),
    "fundamentals.profitability.fcf_margin_ttm": FundamentalGlossaryEntry(
        "fundamentals.profitability.fcf_margin_ttm",
        "FCF Margin (TTM)",
        "TTM free cash flow margin",
        "Profitability",
        "Free cash flow as a percentage of revenue over TTM.",
        "What share of revenue converts to free cash flow?",
        "free_cash_flow_ttm / revenue_ttm * 100",
        ("operating_cash_flow", "capital_expenditure", "revenue"),
        "ttm",
        "percent",
        "percent_2dp",
        "profitability_peer_percentile_v1",
        ("card", "detail"),
        True,
        ("insufficient_quarter_history", "non_positive_revenue", "missing_capex_or_ocf"),
    ),
    # ── Cash flow quality ──────────────────────────────────────────────────
    "fundamentals.cash_flow_quality.cfo_to_net_income_ttm": FundamentalGlossaryEntry(
        "fundamentals.cash_flow_quality.cfo_to_net_income_ttm",
        "CFO / Net Income (TTM)",
        "CFO to net income ratio",
        "Cash Flow Quality",
        "Operating cash flow divided by net income over TTM.",
        "How well do reported earnings translate to operating cash?",
        "operating_cash_flow_ttm / net_income_ttm",
        ("operating_cash_flow", "net_income"),
        "ttm",
        "multiple",
        "multiple_2dp",
        "cash_conversion_v1",
        ("card", "detail"),
        True,
        ("insufficient_quarter_history", "non_positive_net_income"),
    ),
    "fundamentals.cash_flow_quality.fcf_conversion_ttm": FundamentalGlossaryEntry(
        "fundamentals.cash_flow_quality.fcf_conversion_ttm",
        "FCF Conversion (TTM)",
        "FCF to net income ratio",
        "Cash Flow Quality",
        "Free cash flow divided by net income over TTM.",
        "How well do reported earnings translate to free cash flow?",
        "free_cash_flow_ttm / net_income_ttm",
        ("operating_cash_flow", "capital_expenditure", "net_income"),
        "ttm",
        "multiple",
        "multiple_2dp",
        "cash_conversion_v1",
        ("card", "detail"),
        True,
        ("insufficient_quarter_history", "non_positive_net_income", "missing_capex_or_ocf"),
    ),
    # ── Growth ──────────────────────────────────────────────────────────────
    "fundamentals.growth.revenue_yoy_ttm": FundamentalGlossaryEntry(
        "fundamentals.growth.revenue_yoy_ttm",
        "Revenue YoY (TTM)",
        "Year-over-year TTM revenue growth",
        "Growth",
        "Trailing-twelve-month revenue compared to the same TTM one year prior.",
        "Is revenue growing or contracting year-over-year?",
        "revenue_ttm / revenue_ttm_1y_ago - 1",
        ("revenue",),
        "ttm",
        "percent",
        "percent_2dp",
        "growth_yoy_v1",
        ("card", "detail"),
        True,
        ("insufficient_quarter_history", "non_positive_prior_revenue"),
    ),
    "fundamentals.growth.eps_diluted_yoy_ttm": FundamentalGlossaryEntry(
        "fundamentals.growth.eps_diluted_yoy_ttm",
        "EPS Diluted YoY (TTM)",
        "Year-over-year TTM diluted EPS growth",
        "Growth",
        "Trailing-twelve-month diluted EPS compared to the same TTM one year prior.",
        "Is per-share earnings growing or contracting year-over-year?",
        "eps_ttm / eps_ttm_1y_ago - 1",
        ("diluted_eps",),
        "ttm",
        "percent",
        "percent_2dp",
        "growth_yoy_v1",
        ("card", "detail"),
        True,
        ("insufficient_quarter_history", "non_positive_prior_eps"),
    ),
    "fundamentals.growth.ebitda_yoy_ttm": FundamentalGlossaryEntry(
        "fundamentals.growth.ebitda_yoy_ttm",
        "EBITDA YoY (TTM)",
        "Year-over-year TTM EBITDA growth",
        "Growth",
        "Trailing-twelve-month EBITDA compared to the same TTM one year prior.",
        "Is operating cash earnings growing or contracting year-over-year?",
        "ebitda_ttm / ebitda_ttm_1y_ago - 1",
        ("ebitda",),
        "ttm",
        "percent",
        "percent_2dp",
        "growth_yoy_v1",
        ("card", "detail"),
        True,
        ("insufficient_quarter_history", "non_positive_prior_ebitda"),
    ),
    # ── Financial health ───────────────────────────────────────────────────
    "fundamentals.financial_health.cash_and_equivalents_mrq": FundamentalGlossaryEntry(
        "fundamentals.financial_health.cash_and_equivalents_mrq",
        "Cash & Equivalents (MRQ)",
        "Most-recent-quarter cash and equivalents",
        "Financial Health",
        "Cash and short-term investments as of the most recent quarter.",
        "What is the cash position?",
        "latest_available_instant_fact",
        ("cash_and_equivalents",),
        "mrq",
        "currency",
        "currency_2dp",
        "context_only_v1",
        ("card", "detail"),
        True,
        ("no_instant_facts_available",),
    ),
    "fundamentals.financial_health.total_debt_mrq": FundamentalGlossaryEntry(
        "fundamentals.financial_health.total_debt_mrq",
        "Total Debt (MRQ)",
        "Most-recent-quarter total debt",
        "Financial Health",
        "Total debt (short-term plus long-term, or reported) as of the most recent quarter.",
        "What is the debt level?",
        "latest_available_instant_fact or short_term_debt + long_term_debt",
        ("total_debt", "short_term_debt", "long_term_debt"),
        "mrq",
        "currency",
        "currency_2dp",
        "context_only_v1",
        ("card", "detail"),
        True,
        ("no_instant_facts_available",),
    ),
    "fundamentals.financial_health.net_debt_mrq": FundamentalGlossaryEntry(
        "fundamentals.financial_health.net_debt_mrq",
        "Net Debt (MRQ)",
        "Most-recent-quarter net debt",
        "Financial Health",
        "Total debt minus cash and equivalents as of the most recent quarter.",
        "What is the net debt position?",
        "total_debt_mrq - cash_and_equivalents_mrq",
        ("total_debt", "cash_and_equivalents"),
        "mrq",
        "currency",
        "currency_2dp",
        "context_only_v1",
        ("card", "detail"),
        True,
        ("no_instant_facts_available",),
    ),
    "fundamentals.financial_health.net_debt_to_ebitda_ttm": FundamentalGlossaryEntry(
        "fundamentals.financial_health.net_debt_to_ebitda_ttm",
        "Net Debt / EBITDA (TTM)",
        "Net debt to EBITDA ratio",
        "Financial Health",
        "Net debt (MRQ) divided by EBITDA (TTM).",
        "How many years of EBITDA would cover net debt?",
        "net_debt_mrq / ebitda_ttm",
        ("total_debt", "cash_and_equivalents", "ebitda"),
        "ttm",
        "multiple",
        "multiple_2dp",
        "leverage_v1",
        ("card", "detail"),
        True,
        ("no_instant_facts_available", "insufficient_quarter_history", "non_positive_ebitda"),
    ),
    "fundamentals.financial_health.current_ratio_mrq": FundamentalGlossaryEntry(
        "fundamentals.financial_health.current_ratio_mrq",
        "Current Ratio (MRQ)",
        "Most-recent-quarter current ratio",
        "Financial Health",
        "Current assets divided by current liabilities as of the most recent quarter.",
        "Can the business cover short-term obligations?",
        "current_assets / current_liabilities",
        ("current_assets", "current_liabilities"),
        "mrq",
        "multiple",
        "multiple_2dp",
        "liquidity_v1",
        ("card", "detail"),
        True,
        ("no_instant_facts_available", "non_positive_current_liabilities"),
    ),
    "fundamentals.financial_health.debt_to_equity_mrq": FundamentalGlossaryEntry(
        "fundamentals.financial_health.debt_to_equity_mrq",
        "Debt / Equity (MRQ)",
        "Most-recent-quarter debt-to-equity ratio",
        "Financial Health",
        "Total debt divided by total equity as of the most recent quarter.",
        "What is the leverage relative to equity?",
        "total_debt / total_equity",
        ("total_debt", "total_equity"),
        "mrq",
        "multiple",
        "multiple_2dp",
        "debt_to_equity_v1",
        ("card", "detail"),
        True,
        ("no_instant_facts_available", "non_positive_total_equity"),
    ),
    # ── Estimates ────────────────────────────────────────────────────────────
    "fundamentals.estimates.target_price": FundamentalGlossaryEntry(
        "fundamentals.estimates.target_price",
        "Target Price",
        "Analyst consensus price target",
        "Estimates",
        "Mean analyst price target from the latest available consensus.",
        "What is the consensus price target?",
        "latest_analyst_target_mean",
        ("target_mean",),
        "snapshot",
        "currency",
        "currency_2dp",
        "context_only_v1",
        ("card", "detail"),
        True,
        ("no_estimates_data",),
    ),
    "fundamentals.estimates.target_high": FundamentalGlossaryEntry(
        "fundamentals.estimates.target_high",
        "Target High",
        "Highest analyst price target",
        "Estimates",
        "Highest analyst price target from the latest available consensus.",
        "What is the highest price target?",
        "latest_analyst_target_high",
        ("target_high",),
        "snapshot",
        "currency",
        "currency_2dp",
        "context_only_v1",
        ("detail",),
        True,
        ("no_estimates_data",),
    ),
    "fundamentals.estimates.target_low": FundamentalGlossaryEntry(
        "fundamentals.estimates.target_low",
        "Target Low",
        "Lowest analyst price target",
        "Estimates",
        "Lowest analyst price target from the latest available consensus.",
        "What is the lowest price target?",
        "latest_analyst_target_low",
        ("target_low",),
        "snapshot",
        "currency",
        "currency_2dp",
        "context_only_v1",
        ("detail",),
        True,
        ("no_estimates_data",),
    ),
    "fundamentals.estimates.buy_ratio": FundamentalGlossaryEntry(
        "fundamentals.estimates.buy_ratio",
        "Buy Ratio",
        "Ratio of buy to total analyst ratings",
        "Estimates",
        "Percentage of analyst ratings that are buy or strong buy.",
        "What share of analysts recommend buying?",
        "(strong_buy + buy) / (strong_buy + buy + hold + sell + strong_sell) * 100",
        ("strong_buy", "buy", "hold", "sell", "strong_sell"),
        "snapshot",
        "percent",
        "percent_2dp",
        "context_only_v1",
        ("card", "detail"),
        True,
        ("no_estimates_data", "no_ratings_available"),
    ),
    "fundamentals.estimates.forward_eps_growth": FundamentalGlossaryEntry(
        "fundamentals.estimates.forward_eps_growth",
        "Forward EPS Growth",
        "Estimated forward EPS growth rate",
        "Estimates",
        "Projected year-over-year EPS growth based on consensus forward estimates.",
        "What is the expected EPS growth rate?",
        "(forward_eps - trailing_eps) / abs(trailing_eps)",
        ("forward_eps", "trailing_eps"),
        "snapshot",
        "percent",
        "percent_2dp",
        "context_only_v1",
        ("detail",),
        False,
        ("no_source_data",),
    ),
    "fundamentals.estimates.eps_revision_30d": FundamentalGlossaryEntry(
        "fundamentals.estimates.eps_revision_30d",
        "EPS Revision (30d)",
        "30-day consensus EPS estimate revision",
        "Estimates",
        "Percentage change in consensus EPS estimate over the last 30 days.",
        "Are EPS estimates being revised up or down?",
        "(current_eps_estimate - eps_estimate_30d_ago) / abs(eps_estimate_30d_ago)",
        ("current_eps_estimate", "eps_estimate_30d_ago"),
        "snapshot",
        "percent",
        "percent_2dp",
        "estimate_revision_v1",
        ("detail",),
        False,
        ("no_source_data",),
    ),
    "fundamentals.estimates.revenue_revision_30d": FundamentalGlossaryEntry(
        "fundamentals.estimates.revenue_revision_30d",
        "Revenue Revision (30d)",
        "30-day consensus revenue estimate revision",
        "Estimates",
        "Percentage change in consensus revenue estimate over the last 30 days.",
        "Are revenue estimates being revised up or down?",
        "(current_revenue_estimate - revenue_estimate_30d_ago) / abs(revenue_estimate_30d_ago)",
        ("current_revenue_estimate", "revenue_estimate_30d_ago"),
        "snapshot",
        "percent",
        "percent_2dp",
        "estimate_revision_v1",
        ("detail",),
        False,
        ("no_source_data",),
    ),
    # ── Events ───────────────────────────────────────────────────────────────
    "fundamentals.events.days_to_earnings": FundamentalGlossaryEntry(
        "fundamentals.events.days_to_earnings",
        "Days to Earnings",
        "Days until the next confirmed earnings report",
        "Events",
        "Number of calendar days until the next confirmed earnings report date.",
        "How many days until the next earnings report?",
        "next_earnings_report_date - as_of",
        ("earnings_report_date",),
        "snapshot",
        "days",
        "int",
        "proximity_v1",
        ("card", "detail"),
        True,
        ("no_earnings_calendar_data", "no_upcoming_report"),
    ),
    "fundamentals.events.earnings_surprise_pct": FundamentalGlossaryEntry(
        "fundamentals.events.earnings_surprise_pct",
        "Earnings Surprise",
        "Most recent earnings surprise percentage",
        "Events",
        "Percentage difference between actual and estimated EPS for the latest reported quarter.",
        "Did the company beat or miss earnings estimates?",
        "(actual_eps - estimated_eps) / abs(estimated_eps) * 100",
        ("actual_eps", "estimated_eps"),
        "snapshot",
        "percent",
        "percent_2dp",
        "context_only_v1",
        ("detail",),
        False,
        ("no_source_data",),
    ),
    # ── Valuation (read-time) ──────────────────────────────────────────────
    "fundamentals.valuation.price_to_earnings_ttm": FundamentalGlossaryEntry(
        "fundamentals.valuation.price_to_earnings_ttm",
        "P/E (TTM)",
        "Trailing price-to-earnings ratio",
        "Valuation",
        "Latest available price divided by TTM diluted EPS.",
        "What is the price relative to trailing earnings?",
        "price / diluted_eps_ttm",
        ("price", "diluted_eps"),
        "read_time",
        "multiple",
        "multiple_2dp",
        "relative_valuation_multiple_v1",
        ("card", "detail"),
        True,
        (
            "price_unavailable_as_of",
            "diluted_eps_not_materialized",
            "currency_mismatch_without_pit_fx",
            "non_positive_denominator",
        ),
    ),
    "fundamentals.valuation.price_to_sales_ttm": FundamentalGlossaryEntry(
        "fundamentals.valuation.price_to_sales_ttm",
        "P/S (TTM)",
        "Trailing price-to-sales ratio",
        "Valuation",
        "Latest available price divided by TTM revenue per share.",
        "What is the price relative to trailing revenue per share?",
        "price / revenue_per_share_ttm",
        ("price", "revenue"),
        "read_time",
        "multiple",
        "multiple_2dp",
        "relative_valuation_multiple_v1",
        ("card", "detail"),
        True,
        (
            "price_unavailable_as_of",
            "revenue_per_share_not_materialized",
            "currency_mismatch_without_pit_fx",
            "non_positive_denominator",
        ),
    ),
    "fundamentals.valuation.price_to_fcf_ttm": FundamentalGlossaryEntry(
        "fundamentals.valuation.price_to_fcf_ttm",
        "P/FCF (TTM)",
        "Trailing price-to-free-cash-flow ratio",
        "Valuation",
        "Latest available price divided by TTM free cash flow per share.",
        "What is the price relative to trailing free cash flow per share?",
        "price / fcf_per_share_ttm",
        ("price", "operating_cash_flow", "capital_expenditure"),
        "read_time",
        "multiple",
        "multiple_2dp",
        "relative_valuation_multiple_v1",
        ("card", "detail"),
        True,
        (
            "price_unavailable_as_of",
            "fcf_per_share_not_materialized",
            "currency_mismatch_without_pit_fx",
            "non_positive_denominator",
        ),
    ),
    # ── Per-share denominators (not materialized — read-time dependency) ────
    "fundamentals.profitability.diluted_eps_ttm": FundamentalGlossaryEntry(
        "fundamentals.profitability.diluted_eps_ttm",
        "Diluted EPS (TTM)",
        "Trailing-twelve-month diluted EPS",
        "Profitability",
        "Diluted earnings per share over the last four standalone quarters.",
        "What is the per-share earnings?",
        "sum(last_four_standalone_quarter_diluted_eps)",
        ("diluted_eps",),
        "ttm",
        "currency",
        "currency_2dp",
        "context_only_v1",
        ("detail",),
        False,
        ("not_materialized", "insufficient_quarter_history"),
    ),
    "fundamentals.scale.revenue_per_share_ttm": FundamentalGlossaryEntry(
        "fundamentals.scale.revenue_per_share_ttm",
        "Revenue per Share (TTM)",
        "Trailing-twelve-month revenue per share",
        "Scale",
        "Revenue per share over the last four standalone quarters.",
        "What is the per-share revenue?",
        "revenue_ttm / diluted_shares_outstanding",
        ("revenue", "shares_outstanding"),
        "ttm",
        "currency",
        "currency_2dp",
        "context_only_v1",
        ("detail",),
        False,
        ("not_materialized", "insufficient_quarter_history", "no_shares_outstanding"),
    ),
    "fundamentals.cash_flow_quality.fcf_per_share_ttm": FundamentalGlossaryEntry(
        "fundamentals.cash_flow_quality.fcf_per_share_ttm",
        "FCF per Share (TTM)",
        "Trailing-twelve-month free cash flow per share",
        "Cash Flow Quality",
        "Free cash flow per share over the last four standalone quarters.",
        "What is the per-share free cash flow?",
        "free_cash_flow_ttm / diluted_shares_outstanding",
        ("operating_cash_flow", "capital_expenditure", "shares_outstanding"),
        "ttm",
        "currency",
        "currency_2dp",
        "context_only_v1",
        ("detail",),
        False,
        (
            "not_materialized",
            "insufficient_quarter_history",
            "no_shares_outstanding",
            "missing_capex_or_ocf",
        ),
    ),
}

# ── Category labels ───────────────────────────────────────────────────────

FUNDAMENTAL_CATEGORIES: dict[str, str] = {
    "Scale": "Scale",
    "Profitability": "Profitability",
    "Growth": "Growth",
    "Financial Health": "Financial Health",
    "Cash Flow Quality": "Cash Flow Quality",
    "Estimates": "Estimates",
    "Events": "Events",
    "Valuation": "Valuation",
}

# ── State resolution ──────────────────────────────────────────────────────


def resolve_fundamental_state(
    profile: FundamentalThresholdProfile,
    value: float | None,
    *,
    has_peer_baseline: bool = False,
    peer_count: int = 0,
) -> tuple[str, str, str]:
    """Resolve a metric value to (state, tone, label) using the profile.

    For ``context`` profiles: always returns a gray contextual state.
    For ``peer_percentile`` profiles: returns gray ``raw_value`` when peer
    data is insufficient (no baseline, or peer count below ``min_peer_count``).
    For ``discrete`` profiles: matches the first band whose range contains
    the value.
    Returns ``("unavailable", "gray", "unavailable")`` when value is None.
    """
    if value is None:
        return "unavailable", TONE_GRAY, "unavailable"

    if profile.method == "context":
        return "contextual", TONE_GRAY, "contextual"

    if profile.method == "peer_percentile":
        if not has_peer_baseline or peer_count < profile.min_peer_count:
            return "raw_value", TONE_GRAY, "raw value (peer data insufficient)"
        return "raw_value", TONE_GRAY, "raw value (peer data insufficient)"

    for band in profile.bands:
        if _band_matches(band, value):
            return band.state, band.tone, band.label
    return "available", TONE_GRAY, "available"


def get_threshold_profile(profile_id: str) -> FundamentalThresholdProfile | None:
    return FUNDAMENTAL_THRESHOLDS.get(profile_id)


FUNDAMENTALS_OVERVIEW: tuple[str, ...] = (
    "fundamentals.scale.revenue_ttm",
    "fundamentals.valuation.price_to_earnings_ttm",
    "fundamentals.profitability.operating_margin_ttm",
    "fundamentals.profitability.net_margin_ttm",
    "fundamentals.growth.revenue_yoy_ttm",
    "fundamentals.growth.eps_diluted_yoy_ttm",
    "fundamentals.cash_flow_quality.fcf_conversion_ttm",
    "fundamentals.financial_health.current_ratio_mrq",
    "fundamentals.financial_health.net_debt_to_ebitda_ttm",
)


def get_glossary_entry(metric_id: str) -> FundamentalGlossaryEntry | None:
    return FUNDAMENTAL_GLOSSARY.get(metric_id)


def get_metric_threshold_profile_id(metric_id: str) -> str:
    entry = FUNDAMENTAL_GLOSSARY.get(metric_id)
    return entry.threshold_profile_id if entry else ""


def glossary_to_json() -> list[dict[str, Any]]:
    """Return JSON-safe glossary payload for API responses and tooltip lookup."""
    payloads: list[dict[str, Any]] = []
    for entry in FUNDAMENTAL_GLOSSARY.values():
        profile = FUNDAMENTAL_THRESHOLDS.get(entry.threshold_profile_id)
        profile_payload: dict[str, Any] | None = None
        if profile is not None:
            profile_payload = {
                "profile_id": profile.profile_id,
                "version": profile.version,
                "method": profile.method,
                "description": profile.description,
                "min_peer_count": profile.min_peer_count,
                "bands": [
                    {
                        "state": b.state,
                        "tone": b.tone,
                        "label": b.label,
                        "min_value": b.min_value,
                        "max_value": b.max_value,
                    }
                    for b in profile.bands
                ],
            }
        payloads.append(
            {
                "metric_id": entry.metric_id,
                "name": entry.name,
                "full_name": entry.full_name,
                "category": entry.category,
                "description": entry.description,
                "what_it_answers": entry.what_it_answers,
                "formula": entry.formula,
                "inputs": list(entry.inputs),
                "basis": entry.basis,
                "unit": entry.unit,
                "display_formatter": entry.display_formatter,
                "threshold_profile_id": entry.threshold_profile_id,
                "surfaces": list(entry.surfaces),
                "implemented": entry.implemented,
                "unavailable_conditions": list(entry.unavailable_conditions),
                "threshold_profile": profile_payload,
            }
        )
    return payloads


def _band_matches(band: FundamentalBand, value: float) -> bool:
    if band.min_value is not None and value < band.min_value:
        return False
    return not (band.max_value is not None and value >= band.max_value)


__all__ = [
    "FundamentalBand",
    "FundamentalThresholdProfile",
    "FundamentalGlossaryEntry",
    "FUNDAMENTAL_THRESHOLDS",
    "FUNDAMENTAL_GLOSSARY",
    "FUNDAMENTAL_CATEGORIES",
    "resolve_fundamental_state",
    "get_threshold_profile",
    "get_glossary_entry",
    "get_metric_threshold_profile_id",
    "glossary_to_json",
]
