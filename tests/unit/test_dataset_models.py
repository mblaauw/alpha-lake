from datetime import date, datetime

import polars as pl

from alpha_lake.models.dataset_models import (
    EarningsEventFact,
    EntityMentionFact,
    FundamentalFact,
    InsiderTxFact,
    NewsArticleFact,
    SentimentAnnotationFact,
    SocialAttentionFact,
    SocialPostFact,
)
from alpha_lake.normalize.rules import normalize_value, standardize_line_item


def _make(name: str) -> list[str]:
    """Create a DataFrame with default nulls for all optional fields."""
    cols = {
        "FundamentalFact": [
            "security_id",
            "effective_date",
            "available_at",
            "source_id",
            "fiscal_period",
            "statement_type",
            "line_item",
            "value",
            "currency",
            "unit",
            "source_fetch_id",
            "raw_payload_hash",
            "ingestion_run_id",
            "content_hash",
            "version_hash",
            "schema_version",
            "parser_version",
            "quality_status",
        ],
        "InsiderTxFact": [
            "security_id",
            "effective_date",
            "available_at",
            "source_id",
            "filer_cik",
            "issuer_cik",
            "transaction_code",
            "shares",
            "price",
            "value",
            "source_fetch_id",
            "raw_payload_hash",
            "ingestion_run_id",
            "content_hash",
            "version_hash",
            "schema_version",
            "parser_version",
            "quality_status",
        ],
        "NewsArticleFact": [
            "article_id",
            "effective_date",
            "available_at",
            "source_id",
            "title",
            "description",
            "url",
            "text_hash",
            "published_at",
            "source_name",
            "source_fetch_id",
            "raw_payload_hash",
            "ingestion_run_id",
            "content_hash",
            "version_hash",
            "schema_version",
            "parser_version",
            "quality_status",
        ],
        "SocialPostFact": [
            "post_id_hash",
            "effective_date",
            "available_at",
            "source_id",
            "platform",
            "venue",
            "parent_id_hash",
            "text_hash",
            "published_at",
            "engagement_json",
            "source_fetch_id",
            "raw_payload_hash",
            "ingestion_run_id",
            "content_hash",
            "version_hash",
            "schema_version",
            "parser_version",
            "quality_status",
        ],
        "EarningsEventFact": [
            "security_id",
            "effective_date",
            "available_at",
            "source_id",
            "report_date",
            "session",
            "source_fetch_id",
            "raw_payload_hash",
            "ingestion_run_id",
            "content_hash",
            "version_hash",
            "schema_version",
            "parser_version",
            "quality_status",
        ],
        "EntityMentionFact": [
            "mention_id",
            "effective_date",
            "available_at",
            "text_item_id",
            "text_item_type",
            "security_id",
            "entity_name",
            "entity_type",
            "confidence",
            "match_method",
            "source_fetch_id",
            "raw_payload_hash",
            "ingestion_run_id",
            "content_hash",
            "version_hash",
            "schema_version",
            "parser_version",
            "quality_status",
        ],
        "SentimentAnnotationFact": [
            "annotation_id",
            "effective_date",
            "available_at",
            "source_id",
            "annotation_kind",
            "sentiment_score",
            "sentiment_label",
            "model_version",
            "prompt_version",
            "taxonomy_version",
            "input_text_hash",
            "source_dataset_version",
            "security_id",
            "source_fetch_id",
            "raw_payload_hash",
            "ingestion_run_id",
            "content_hash",
            "version_hash",
            "schema_version",
            "parser_version",
            "quality_status",
        ],
        "SocialAttentionFact": [
            "security_id",
            "effective_date",
            "available_at",
            "source_id",
            "cohort",
            "mentions",
            "mentions_24h_ago",
            "upvotes",
            "rank",
            "rank_24h_ago",
            "name",
            "source_fetch_id",
            "raw_payload_hash",
            "ingestion_run_id",
            "content_hash",
            "version_hash",
            "schema_version",
            "parser_version",
            "quality_status",
        ],
    }
    return cols.get(name, [])


def _df(model_name: str, extra: dict) -> pl.DataFrame:
    data = {c: [None] for c in _make(model_name)}
    for k, v in extra.items():
        data[k] = [v]
    return pl.DataFrame(data)


def _td(name: str, **kw) -> pl.DataFrame:
    cols = _make(name)
    string_cols = {
        "source_fetch_id",
        "raw_payload_hash",
        "ingestion_run_id",
        "content_hash",
        "version_hash",
        "quality_status",
        "currency",
        "unit",
        "session",
        "parent_id_hash",
        "engagement_json",
        "source_name",
        "description",
        "model_version",
        "prompt_version",
        "taxonomy_version",
        "input_text_hash",
        "source_dataset_version",
        "security_id",
        "name",
    }
    int_cols = {
        "schema_version",
        "parser_version",
        "upvotes",
        "article_count",
        "mention_count",
        "unique_source_count",
        "unique_author_count",
        "mentions",
        "mentions_24h_ago",
    }
    float_cols = {
        "value",
        "shares",
        "price",
        "confidence",
        "sentiment_score",
        "mean_sentiment",
        "sentiment_std",
        "positive_share",
        "neutral_share",
        "negative_share",
        "velocity_score",
    }
    date_cols = {"window_start", "window_end", "report_date", "effective_date"}
    dt_cols = {"available_at", "published_at", "source_published_at", "ingested_at", "validated_at"}

    data = {}
    for c in cols:
        if c in kw:
            data[c] = [kw[c]]
        elif c in string_cols:
            data[c] = [""]
        elif c in int_cols:
            data[c] = [0]
        elif c in float_cols:
            data[c] = [0.0]
        elif c in date_cols:
            data[c] = [date(2020, 1, 1)]
        elif c in dt_cols:
            data[c] = [datetime(2020, 1, 1, 12, 0)]
        elif c == "effective_date":
            data[c] = [date(2020, 1, 1)]
        else:
            data[c] = [None]
    df = pl.DataFrame(data)
    for c in df.columns:
        if df[c].dtype == pl.Null:
            df = df.with_columns(pl.col(c).cast(pl.Datetime))
    return df


def test_fundamental_fact():
    df = _td(
        "FundamentalFact",
        security_id="sec_t",
        effective_date=date(2025, 1, 1),
        available_at=datetime(2025, 1, 2, 12, 0),
        source_id="sec",
        fiscal_period="2024Q4",
        statement_type="BS",
        line_item="Assets",
        value=1000000.0,
    )
    assert FundamentalFact.validate(df).height == 1


def test_insider_tx_fact():
    df = _td(
        "InsiderTxFact",
        security_id="sec_t",
        effective_date=date(2025, 1, 1),
        available_at=datetime(2025, 1, 2, 12, 0),
        source_id="sec",
        filer_cik="0001",
        issuer_cik="0002",
        transaction_code="P",
        shares=1000.0,
        price=50.0,
        value=50000.0,
    )
    assert InsiderTxFact.validate(df).height == 1


def test_news_article_fact():
    df = _td(
        "NewsArticleFact",
        article_id="a1",
        effective_date=date(2025, 1, 1),
        available_at=datetime(2025, 1, 2, 12, 0),
        source_id="tiingo",
        title="Test",
        url="https://example.com",
        text_hash="abc",
        source_name="TS",
    )
    assert NewsArticleFact.validate(df).height == 1


def test_earnings_event_fact():
    df = _td(
        "EarningsEventFact",
        security_id="sec_t",
        effective_date=date(2025, 1, 1),
        available_at=datetime(2025, 1, 2, 12, 0),
        source_id="eodhd",
        report_date=date(2025, 1, 15),
    )
    assert EarningsEventFact.validate(df).height == 1


def test_social_post_fact():
    df = _td(
        "SocialPostFact",
        post_id_hash="p1",
        effective_date=date(2025, 1, 1),
        available_at=datetime(2025, 1, 2, 12, 0),
        source_id="reddit",
        platform="reddit",
        venue="r/test",
        text_hash="abc",
    )
    assert SocialPostFact.validate(df).height == 1


def test_entity_mention_fact():
    df = _td(
        "EntityMentionFact",
        mention_id="m1",
        effective_date=date(2025, 1, 1),
        available_at=datetime(2025, 1, 2, 12, 0),
        text_item_id="a1",
        text_item_type="news_article",
        security_id="sec_t",
        entity_name="Apple",
        entity_type="ORG",
        confidence=0.95,
        match_method="exact",
    )
    assert EntityMentionFact.validate(df).height == 1


def test_sentiment_annotation_fact():
    df = _td(
        "SentimentAnnotationFact",
        annotation_id="ann1",
        effective_date=date(2025, 1, 1),
        available_at=datetime(2025, 1, 2, 12, 0),
        source_id="stocktwits",
        annotation_kind="message_tag",
        sentiment_score=0.5,
        sentiment_label="Bullish",
        security_id="",
    )
    assert SentimentAnnotationFact.validate(df).height == 1


def test_social_attention_fact():
    df = _td(
        "SocialAttentionFact",
        security_id="sec_t",
        effective_date=date(2025, 1, 1),
        available_at=datetime(2025, 1, 2, 12, 0),
        source_id="apewisdom",
        cohort="wallstreetbets",
        mentions=100,
        mentions_24h_ago=80,
        upvotes=500,
        rank=1,
        rank_24h_ago=2,
    )
    assert SocialAttentionFact.validate(df).height == 1


def test_normalize_value():
    assert normalize_value(100, "USD") == 100.0
    assert normalize_value(100, "EUR") == 105.0


def test_standardize_line_item():
    assert standardize_line_item("Total Assets") == "Assets"
    assert standardize_line_item("EPS") == "EarningsPerShare"
    assert standardize_line_item("custom_item") == "custom_item"
