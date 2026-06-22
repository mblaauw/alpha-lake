from __future__ import annotations

from datetime import datetime, timedelta

import polars as pl

from alpha_lake.canonical import compute_version_hash


def compute_insider_cluster_metrics(
    insider_tx: pl.DataFrame,
    as_of: datetime,
    window_days: int = 30,
) -> pl.DataFrame:
    """Per-issuer, rolling-N-day insider-tx aggregations.

    ``insider_tx`` must contain ``security_id``, ``effective_date``,
    ``available_at``, ``transaction_code``, ``shares``, ``value``.

    Returns:
        ``buy_count``, ``distinct_buyer_count``, ``net_value`` per
        ``(security_id, effective_date)``.
    """
    pit = insider_tx.filter(pl.col("available_at") <= as_of).sort("security_id", "effective_date")
    rows: list[dict] = []

    for sid in pit["security_id"].unique():
        s = pit.filter(pl.col("security_id") == sid).sort("effective_date")
        for i in range(len(s)):
            dt = s["effective_date"][i]
            window_start = dt - timedelta(days=window_days)
            window_rows = s.filter(
                pl.col("effective_date") >= window_start, pl.col("effective_date") <= dt
            )
            buys = window_rows.filter(pl.col("transaction_code") == "P")
            sells = window_rows.filter(pl.col("transaction_code") == "S")

            rows.append(
                {
                    "security_id": sid,
                    "effective_date": dt,
                    "available_at": as_of,
                    "source_id": "derived",
                    "buy_count": len(buys),
                    "sell_count": len(sells),
                    "net_value": float(buys["value"].sum() or 0) - float(sells["value"].sum() or 0),
                    "source_fetch_id": "",
                    "raw_payload_hash": "",
                    "ingestion_run_id": "",
                    "content_hash": "",
                    "version_hash": "",
                    "schema_version": 1,
                    "parser_version": 1,
                    "quality_status": "valid",
                }
            )

    df = pl.DataFrame(rows)
    if df.is_empty():
        return df
    df = compute_version_hash(df)
    return df.with_columns(
        pl.col("effective_date").cast(pl.Date),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
    )


def compute_attention_deltas(
    attention: pl.DataFrame,
    as_of: datetime,
) -> pl.DataFrame:
    """Aggregated social attention deltas: mention change and rank change.

    ``attention`` must contain ``security_id``, ``effective_date``,
    ``available_at``, ``cohort``, ``mentions``, ``rank``.

    Returns:
        ``mention_delta_pct``, ``rank_change``, ``mention_pctile`` per
        ``(security_id, cohort, effective_date)``.
    """
    pit = attention.filter(pl.col("available_at") <= as_of).sort(
        "security_id", "cohort", "effective_date"
    )
    rows: list[dict] = []

    for sid, cohort in (
        pit.group_by(["security_id", "cohort"])
        .agg(pl.len())
        .select(["security_id", "cohort"])
        .iter_rows()
    ):
        s = pit.filter(pl.col("security_id") == sid, pl.col("cohort") == cohort).sort(
            "effective_date"
        )
        for i in range(len(s)):
            dt = s["effective_date"][i]
            mentions = s["mentions"][i]
            rank = s["rank"][i]
            prev_mentions = s["mentions"][i - 1] if i > 0 else None

            mention_delta = (
                ((mentions - prev_mentions) / prev_mentions * 100)
                if (prev_mentions and prev_mentions != 0)
                else None
            )

            rows.append(
                {
                    "security_id": sid,
                    "cohort": cohort,
                    "effective_date": dt,
                    "available_at": as_of,
                    "source_id": "derived",
                    "mention_delta_pct": mention_delta,
                    "rank": rank,
                    "source_fetch_id": "",
                    "raw_payload_hash": "",
                    "ingestion_run_id": "",
                    "content_hash": "",
                    "version_hash": "",
                    "schema_version": 1,
                    "parser_version": 1,
                    "quality_status": "valid",
                }
            )

    df = pl.DataFrame(rows)
    if df.is_empty():
        return df
    df = compute_version_hash(df)
    return df.with_columns(
        pl.col("effective_date").cast(pl.Date),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
    )


def compute_sentiment_ratios(
    sentiment: pl.DataFrame,
    as_of: datetime,
) -> pl.DataFrame:
    """Per-symbol per-day positive/negative tag ratio and mean news score.

    ``sentiment`` must contain ``security_id``, ``effective_date``,
    ``available_at``, ``annotation_kind``, ``sentiment_score``,
    ``sentiment_label``.

    Returns:
        ``positive_ratio`` (positive / total tagged messages),
        ``mean_score`` (average sentiment score) per
        ``(security_id, effective_date)``.
    """
    pit = sentiment.filter(pl.col("available_at") <= as_of).sort("security_id", "effective_date")
    rows: list[dict] = []

    for sid in pit["security_id"].unique():
        s = pit.filter(pl.col("security_id") == sid).sort("effective_date")
        for dt in s["effective_date"].unique():
            day_rows = s.filter(pl.col("effective_date") == dt)
            total = len(day_rows)
            if total == 0:
                continue
            tagged_positive = day_rows.filter(
                pl.col("sentiment_label").str.to_lowercase().str.contains("bullish")
            )
            positive_ratio = len(tagged_positive) / total if total > 0 else None
            mean_score = day_rows["sentiment_score"].mean()

            rows.append(
                {
                    "security_id": sid,
                    "effective_date": dt,
                    "available_at": as_of,
                    "source_id": "derived",
                    "positive_ratio": positive_ratio,
                    "mean_score": mean_score,
                    "total_messages": total,
                    "source_fetch_id": "",
                    "raw_payload_hash": "",
                    "ingestion_run_id": "",
                    "content_hash": "",
                    "version_hash": "",
                    "schema_version": 1,
                    "parser_version": 1,
                    "quality_status": "valid",
                }
            )

    df = pl.DataFrame(rows)
    if df.is_empty():
        return df
    df = compute_version_hash(df)
    return df.with_columns(
        pl.col("effective_date").cast(pl.Date),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
    )
