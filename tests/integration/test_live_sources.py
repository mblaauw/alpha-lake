"""Live API integration tests.

These tests fetch from real APIs and run the normalize pipeline.
Skipped by default; run with ``pytest --run-live`` or ``just test-integration``.
Results are cached to ``tests/fixtures/live/`` so repeated runs don't hit the API.
"""

from __future__ import annotations

import pytest

from tests.fixtures import cached_fetch, cached_normalize

# ── FRED (keyless) ────────────────────────────────────────────────────────────


@pytest.mark.live
def test_fred_macro_series_fetch():
    """FRED keyless: can fetch raw GDP series."""
    body = cached_fetch("fred", "macro_series", series_id="GDP")
    assert len(body) > 50


@pytest.mark.live
def test_fred_macro_series_normalize():
    """FRED keyless: raw data normalizes to valid schema."""
    df = cached_normalize("fred", "macro_series", series_id="GDP")
    assert df.is_empty() is False
    assert "series_id" in df.columns
    assert "effective_date" in df.columns
    assert "value" in df.columns
    assert df["series_id"][0] == "GDP"
    assert df["value"][0] > 0


# ── StockTwits (keyless) ──────────────────────────────────────────────────────


@pytest.mark.live
def test_stocktwits_sentiment_fetch():
    """StockTwits keyless: can fetch raw sentiment stream for AAPL."""
    body = cached_fetch("stocktwits", "sentiment", symbol="AAPL")
    assert len(body) > 50


@pytest.mark.live
def test_stocktwits_sentiment_normalize():
    """StockTwits keyless: messages normalize to SentimentAnnotationFact."""
    df = cached_normalize(
        "stocktwits",
        "sentiment",
        extract_key="messages",
        security_id="AAPL",
        symbol="AAPL",
    )
    assert df.is_empty() is False
    assert "annotation_id" in df.columns
    assert "sentiment_score" in df.columns
    assert df["security_id"].to_list().count("AAPL") > 0


# ── ApeWisdom (keyless) ───────────────────────────────────────────────────────


@pytest.mark.live
def test_apewisdom_attention_fetch():
    """ApeWisdom keyless: can fetch raw all-stocks list."""
    body = cached_fetch("apewisdom", "attention_metrics", ticker="AAPL")
    assert len(body) > 10


@pytest.mark.live
def test_apewisdom_attention_normalize():
    """ApeWisdom keyless: raw data normalizes to SocialAttentionFact."""
    df = cached_normalize(
        "apewisdom",
        "attention_metrics",
        extract_key="results",
        security_id="AAPL",
    )
    if df.is_empty():
        pytest.skip("AAPL not trending on ApeWisdom right now")
    assert "security_id" in df.columns
    assert "mentions" in df.columns
    assert "rank" in df.columns


# ── Finnhub (keyed) ────────────────────────────────────────────────────────────


@pytest.mark.live
def test_finnhub_news_fetch():
    """Finnhub: can fetch company news for AAPL."""
    body = cached_fetch("finnhub", "news", symbol="AAPL", _from="2026-06-20", _to="2026-06-22")
    assert len(body) > 20


@pytest.mark.live
def test_finnhub_news_normalize():
    """Finnhub: news normalizes to NewsArticleFact."""
    df = cached_normalize(
        "finnhub",
        "news",
        security_id="AAPL",
        symbol="AAPL",
        _from="2026-06-20",
        _to="2026-06-22",
    )
    if df.is_empty():
        pytest.skip("No Finnhub news for AAPL in date range")
    assert "article_id" in df.columns
    assert "title" in df.columns
    assert all(a.startswith("finnhub_") for a in df["article_id"].to_list())


@pytest.mark.live
def test_finnhub_insider_tx_normalize():
    """Finnhub: insider sentiment normalizes to InsiderTxFact."""
    df = cached_normalize(
        "finnhub",
        "insider_tx",
        extract_key="data",
        security_id="AAPL",
        symbol="AAPL",
    )
    if df.is_empty():
        pytest.skip("No Finnhub insider data for AAPL")
    assert "security_id" in df.columns
    assert "shares" in df.columns


# ── Marketaux (keyed) ──────────────────────────────────────────────────────────


@pytest.mark.live
def test_marketaux_news_fetch():
    """Marketaux: can fetch news for AAPL."""
    body = cached_fetch(
        "marketaux",
        "news",
        symbols="AAPL",
        published_after="2026-06-20",
        published_before="2026-06-22",
        limit="3",
    )
    assert len(body) > 50


@pytest.mark.live
def test_marketaux_news_normalize():
    """Marketaux: news normalizes to NewsArticleFact."""
    df = cached_normalize(
        "marketaux",
        "news",
        extract_key="data",
        security_id="AAPL",
        symbols="AAPL",
        published_after="2026-06-20",
        published_before="2026-06-22",
        limit="3",
    )
    if df.is_empty():
        pytest.skip("No Marketaux news for AAPL in date range")
    assert "article_id" in df.columns
    assert "title" in df.columns


@pytest.mark.live
def test_marketaux_sentiment_normalize():
    """Marketaux: entity-level sentiment normalizes with real scores."""
    df = cached_normalize(
        "marketaux",
        "sentiment",
        extract_key="data",
        security_id="AAPL",
        symbols="AAPL",
        published_after="2026-06-20",
        published_before="2026-06-22",
        limit="3",
    )
    if df.is_empty():
        pytest.skip("No Marketaux sentiment for AAPL in date range")
    assert "sentiment_score" in df.columns
    non_null = df.filter(~df["sentiment_score"].is_null())
    if non_null.height > 0:
        assert all(0 <= s <= 1 for s in non_null["sentiment_score"] if s is not None)
