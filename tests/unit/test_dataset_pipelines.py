from datetime import UTC, date, datetime

import duckdb
import polars as pl

from alpha_lake.canonical import write_dataset
from alpha_lake.models.dataset_models import (
    AttentionMetricFact,
    EarningsEventFact,
    EntityMentionFact,
    FundamentalFact,
    InsiderTxFact,
    NewsArticleFact,
    SentimentAnnotationFact,
    SocialPostFact,
)


def _mk(table: str, **kw) -> pl.DataFrame:
    """Create a valid DataFrame for any dataset model."""
    models = {
        "fundamentals": FundamentalFact, "insider_tx": InsiderTxFact,
        "earnings_calendar": EarningsEventFact, "news_articles": NewsArticleFact,
        "social_posts": SocialPostFact, "entity_mentions": EntityMentionFact,
        "sentiment_annotations": SentimentAnnotationFact,
        "attention_metrics": AttentionMetricFact,
    }
    model = models[table]
    ts = datetime(2025, 6, 1, 16, 0, tzinfo=UTC)
    defaults = {
        "available_at": ts, "source_fetch_id": "", "raw_payload_hash": "",
        "ingestion_run_id": "", "content_hash": "", "version_hash": "",
        "schema_version": 1, "parser_version": 1, "quality_status": "valid",
        "effective_date": date(2025, 1, 15),
    }
    data = {}
    for col in model.columns:
        if col in kw:
            data[col] = [kw[col]]
        elif col in defaults:
            data[col] = [defaults[col]]
        else:
            field_info = model.model_fields.get(col)
            if field_info is not None and not field_info.is_required():
                data[col] = [field_info.default]
            else:
                data[col] = [None]
    df = pl.DataFrame(data)
    for c in df.columns:
        if df[c].dtype == pl.Null:
            df = df.with_columns(pl.col(c).cast(pl.Datetime))
    return df


def test_write_datasets():
    con = duckdb.connect()
    con.execute("SET timezone = 'UTC'")
    con.execute("INSTALL ducklake")
    con.execute("LOAD ducklake")
    con.execute("INSTALL sqlite")
    con.execute("LOAD sqlite")

    cases = [
        ("fundamentals", dict(security_id="sec_t", source_id="sec",
            fiscal_period="2024Q4", statement_type="BS", line_item="Assets", value=1e6)),
        ("insider_tx", dict(security_id="sec_t", source_id="sec",
            filer_cik="0001", issuer_cik="0002", transaction_code="P", shares=1000.0, price=50.0, value=50000.0)),
        ("earnings_calendar", dict(security_id="sec_t", source_id="eodhd", report_date=date(2025, 1, 15))),
        ("news_articles", dict(article_id="a1", source_id="tiingo", title="Test", url="https://ex.com",
            text_hash="abc", source_name="TS")),
        ("social_posts", dict(post_id_hash="p1", source_id="reddit", platform="reddit", venue="r/t", text_hash="abc")),
            ("entity_mentions", dict(mention_id="m1", source_id="tiingo",
                text_item_id="a1", text_item_type="news_article", security_id="sec_t",
                entity_name="Apple", entity_type="ORG", confidence=0.9, match_method="exact")),
            ("sentiment_annotations", dict(annotation_id="ann1", source_id="llm",
                text_item_id="a1", text_item_type="news_article",
                sentiment_score=0.5, sentiment_label="positive",
                model_version="v1", prompt_version="v1", taxonomy_version="v1",
                input_text_hash="abc", source_dataset_version="1")),
            ("attention_metrics", dict(security_id="sec_t", source_id="lake",
            window_start=date(2025, 1, 1), window_end=date(2025, 1, 3), window_type="3d",
            article_count=5, mention_count=10, unique_source_count=3, unique_author_count=2)),
    ]

    for table, kw in cases:
        df = _mk(table, **kw)
        count = write_dataset(con, table, df)
        _r = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        assert _r is not None
        row = _r[0]
        assert count == 1
        assert row == 1, f"{table}: expected 1 row, got {row}"

    con.close()
