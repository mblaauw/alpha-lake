from __future__ import annotations

import hashlib
from datetime import datetime

import duckdb
import polars as pl

from alpha_lake.derived.annotations import compute_attention_metrics, compute_sentiment, extract_entities
from alpha_lake.interop import duckdb_to_polars


def get_text_items(
    con: duckdb.DuckDBPyConnection,
    security_id: str,
    as_of: datetime,
    limit: int = 100,
) -> pl.DataFrame:
    """Return PIT-bounded news articles and social posts for a security."""
    rows = con.execute("""
        SELECT article_id AS text_id, 'news_article' AS source_type,
               title, description, url, published_at, source_name
        FROM news_articles
        WHERE security_id = ?
          AND available_at <= CAST(? AS TIMESTAMPTZ)
        LIMIT ?
    """, [security_id, as_of, limit]).fetchall()
    if not rows:
        return pl.DataFrame()

    df = pl.DataFrame({
        "text_id": [r[0] for r in rows],
        "source_type": [r[1] for r in rows],
        "title": [r[2] for r in rows],
        "description": [r[3] for r in rows],
        "url": [r[4] for r in rows],
        "published_at": [r[5] for r in rows],
        "source_name": [r[6] for r in rows],
    })
    return df


def annotate_text_items(df: pl.DataFrame) -> pl.DataFrame:
    """Run neutral NLP annotation on text items.

    Returns entity_mentions-style DataFrame.
    """
    rows = []
    for row in df.iter_rows(named=True):
        text = f"{row.get('title', '')} {row.get('description', '')}"
        sentiment = compute_sentiment(text)
        entities = extract_entities(text)
        for ent in entities:
            rows.append({
                "mention_id": hashlib.sha256(
                    f"{row['text_id']}_{ent['name']}_{ent['type']}".encode()
                ).hexdigest()[:32],
                "text_item_id": row["text_id"],
                "text_item_type": row["source_type"],
                "entity_name": ent["name"],
                "entity_type": ent["type"],
                "confidence": ent["confidence"],
            })

    if not rows:
        return pl.DataFrame()
    return pl.DataFrame(rows)
