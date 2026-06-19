from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timedelta
from typing import Any

import polars as pl
from datetime import timezone

from alpha_lake.derived.indicators import ema

_COMMON_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "shall", "can", "need",
    "dare", "ought", "used", "it", "its", "this", "that", "these", "those",
}


def extract_entities(text: str) -> list[dict[str, Any]]:
    """Simple entity extraction using pattern matching.

    This is a neutral, deterministic approach. No ML models are used.
    Identifies: ticker patterns ($AAPL), uppercase words, URLs.
    """
    entities: list[dict[str, Any]] = []
    for match in re.finditer(r"\$([A-Z]{1,5})", text):
        entities.append({
            "name": match.group(1),
            "type": "ticker",
            "confidence": 0.7,
        })
    for match in re.finditer(r"\b([A-Z][a-z]+ [A-Z][a-z]+)\b", text):
        if not any(w.lower() in _COMMON_WORDS for w in match.group(1).split()):
            entities.append({
                "name": match.group(1),
                "type": "ORG",
                "confidence": 0.5,
            })
    return entities


def compute_sentiment(text: str) -> dict[str, Any]:
    """Simple lexicon-based sentiment scoring.

    Returns score in [-1, 1] and a label (positive/neutral/negative).
    This is a neutral measurement — not a trading signal.
    """
    positive_words = {"buy", "up", "gain", "profit", "growth", "bullish",
        "positive", "strong", "beat", "upgrade", "outperform", "opportunity",
        "momentum", "breakout", "rally", "surge", "rebound", "upward"}
    negative_words = {"sell", "down", "loss", "decline", "bearish", "negative",
        "weak", "miss", "downgrade", "underperform", "risk", "volatile",
        "plunge", "crash", "drop", "fall", "slump", "downturn", "correction"}

    words = set(re.findall(r"\b[a-zA-Z]+\b", text.lower()))
    pos_count = len(words & positive_words)
    neg_count = len(words & negative_words)
    total = pos_count + neg_count
    if total == 0:
        return {"score": 0.0, "label": "neutral"}
    score = (pos_count - neg_count) / total
    label = "positive" if score > 0.2 else ("negative" if score < -0.2 else "neutral")
    return {"score": round(score, 4), "label": label}


def compute_attention_metrics(
    df: pl.DataFrame,
    window_days: int = 1,
) -> pl.DataFrame:
    """Compute attention metrics for a text item DataFrame.

    Input must have: security_id, published_at columns.
    Output: article_count, mention_count, unique_source_count,
    unique_author_count, mean_sentiment, velocity_score.
    """
    if df.height == 0:
        return df

    security_ids = df["security_id"].unique().to_list()
    rows = []
    for sid in security_ids:
        subset = df.filter(pl.col("security_id") == sid)
        rows.append({
            "security_id": sid,
            "effective_date": date.today(),
            "available_at": datetime.now(timezone.utc),
            "window_start": date.today() - timedelta(days=window_days),
            "window_end": date.today(),
            "window_type": f"{window_days}d",
            "article_count": subset.height,
            "mention_count": subset.height,
            "unique_source_count": subset["source_id"].n_unique() if "source_id" in subset.columns else 0,
            "unique_author_count": subset["source_name"].n_unique() if "source_name" in subset.columns else 0,
            "mean_sentiment": subset["sentiment_score"].mean() if "sentiment_score" in subset.columns else None,
            "sentiment_std": subset["sentiment_score"].std() if "sentiment_score" in subset.columns else None,
            "velocity_score": None,
        })
    return pl.DataFrame(rows)
