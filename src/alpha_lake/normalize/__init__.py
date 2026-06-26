from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import polars as pl


def _meta(
    source_fetch_id: str,
    content_hash: str,
    ingestion_run_id: str,
) -> dict[str, Any]:
    """Common lineage metadata fields for every canonical row."""
    return {
        "source_fetch_id": source_fetch_id,
        "raw_payload_hash": content_hash,
        "ingestion_run_id": ingestion_run_id,
        "content_hash": content_hash,
        "version_hash": "",
        "schema_version": 1,
        "parser_version": 1,
        "quality_status": "valid",
    }


def macro_series_from_json(
    raw: list[dict[str, Any]],
    series_id: str,
    source_id: str,
    source_fetch_id: str,
    ingestion_run_id: str,
    content_hash: str,
    available_at: datetime,
) -> pl.DataFrame:
    rows = []
    for record in raw:
        val = record.get("value", "")
        if val in ("", "."):
            continue
        rows.append(
            {
                "series_id": series_id,
                "effective_date": record.get("date"),
                "available_at": available_at,
                "source_id": source_id,
                "value": float(val),
                **_meta(source_fetch_id, content_hash, ingestion_run_id),
            }
        )

    df = pl.DataFrame(rows)
    if df.is_empty():
        return pl.DataFrame()
    return df.with_columns(
        pl.col("effective_date").str.to_date("%Y-%m-%d"),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
    )


def economic_calendar_from_json(
    raw: list[dict[str, Any]],
    source_id: str,
    source_fetch_id: str,
    ingestion_run_id: str,
    content_hash: str,
    available_at: datetime,
) -> pl.DataFrame:
    rows = []
    for record in raw:
        event_date = record.get("date") or record.get("eventDate") or ""
        event_name = record.get("event") or record.get("eventName") or ""
        if not event_date or not event_name:
            continue
        rows.append(
            {
                "event_id": f"{source_id}_{event_name}_{event_date}",
                "effective_date": event_date,
                "available_at": available_at,
                "source_id": source_id,
                "country": record.get("country", "US"),
                **_meta(source_fetch_id, content_hash, ingestion_run_id),
            }
        )

    df = pl.DataFrame(rows)
    if df.is_empty():
        return pl.DataFrame()
    return df.with_columns(
        pl.col("effective_date").str.to_date("%Y-%m-%d"),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
    )


def bars_from_json(
    raw: list[dict[str, Any]],
    security_id: str,
    source_id: str,
    source_fetch_id: str,
    ingestion_run_id: str,
    content_hash: str,
    available_at: datetime,
    ingested_at: datetime | None = None,
) -> pl.DataFrame:
    rows = []
    for record in raw:
        rows.append(
            {
                "security_id": security_id,
                "effective_date": record.get("date"),
                "available_at": available_at,
                "source_id": source_id,
                "source_published_at": None,
                "ingested_at": ingested_at or available_at,
                "validated_at": None,
                "open": float(record.get("open", 0)),
                "high": float(record.get("high", 0)),
                "low": float(record.get("low", 0)),
                "close": float(record.get("close", 0)),
                "volume": int(record.get("volume", 0)),
                **_meta(source_fetch_id, content_hash, ingestion_run_id),
            }
        )

    df = pl.DataFrame(rows)
    if df.is_empty():
        return pl.DataFrame()
    return df.with_columns(
        pl.col("effective_date").str.replace(r"T.*$", "").str.to_date("%Y-%m-%d"),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("source_published_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("ingested_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("validated_at").cast(pl.Datetime(time_zone="UTC")),
    )


def news_from_json(
    raw: list[dict[str, Any]],
    source_id: str,
    source_fetch_id: str,
    ingestion_run_id: str,
    content_hash: str,
    available_at: datetime,
) -> pl.DataFrame:
    rows = []
    for record in raw:
        article_id = record.get("id")
        if not article_id:
            continue
        epoch = record.get("datetime", 0)
        title = record.get("headline", "")
        rows.append(
            {
                "article_id": f"{source_id}_{article_id}",
                "effective_date": _epoch_to_date(epoch),
                "available_at": available_at,
                "source_id": source_id,
                "title": title,
                "description": record.get("summary", ""),
                "url": record.get("url", ""),
                "text_hash": _text_hash(title, record.get("summary", "")),
                "published_at": _epoch_to_dt(epoch),
                "source_name": record.get("source", ""),
                **_meta(source_fetch_id, content_hash, ingestion_run_id),
            }
        )
    df = pl.DataFrame(rows)
    if df.is_empty():
        return pl.DataFrame()
    return df.with_columns(
        pl.col("effective_date").str.to_date("%Y-%m-%d"),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("published_at").cast(pl.Datetime(time_zone="UTC")),
    )


def sentiment_from_news(
    raw: list[dict[str, Any]],
    source_id: str,
    source_fetch_id: str,
    ingestion_run_id: str,
    content_hash: str,
    available_at: datetime,
) -> pl.DataFrame:
    rows = []
    for record in raw:
        article_id = record.get("id")
        if not article_id:
            continue
        epoch = record.get("datetime", 0)
        rows.append(
            {
                "annotation_id": f"{source_id}_{article_id}",
                "effective_date": _epoch_to_date(epoch),
                "available_at": available_at,
                "source_id": source_id,
                "annotation_kind": "news_sentiment",
                "sentiment_score": None,
                "sentiment_label": "",
                "model_version": None,
                "prompt_version": None,
                "taxonomy_version": None,
                "input_text_hash": _text_hash(
                    record.get("headline", ""), record.get("summary", "")
                ),
                "source_dataset_version": None,
                "security_id": record.get("related", ""),
                **_meta(source_fetch_id, content_hash, ingestion_run_id),
            }
        )
    df = pl.DataFrame(rows)
    if df.is_empty():
        return pl.DataFrame()
    return df.with_columns(
        pl.col("effective_date").str.to_date("%Y-%m-%d"),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
    )


def marketaux_news_from_json(
    raw: list[dict[str, Any]],
    source_id: str,
    source_fetch_id: str,
    ingestion_run_id: str,
    content_hash: str,
    available_at: datetime,
) -> pl.DataFrame:
    rows = []
    for record in raw:
        art_id = record.get("uuid")
        if not art_id:
            continue
        pub = record.get("published_at", "")
        rows.append(
            {
                "article_id": f"{source_id}_{art_id}",
                "effective_date": pub[:10] if pub else "",
                "available_at": available_at,
                "source_id": source_id,
                "title": record.get("title", ""),
                "description": (record.get("description") or record.get("snippet") or ""),
                "url": record.get("url", ""),
                "text_hash": _text_hash(record.get("title", ""), record.get("description", "")),
                "published_at": _parse_iso_dt(pub) if pub else available_at,
                "source_name": record.get("source", ""),
                **_meta(source_fetch_id, content_hash, ingestion_run_id),
            }
        )
    if not rows:
        return pl.DataFrame()
    df = pl.DataFrame(rows)
    return df.with_columns(
        pl.col("effective_date").str.to_date("%Y-%m-%d"),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("published_at").cast(pl.Datetime(time_zone="UTC")),
    )


def marketaux_sentiment_from_json(
    raw: list[dict[str, Any]],
    source_id: str,
    source_fetch_id: str,
    ingestion_run_id: str,
    content_hash: str,
    available_at: datetime,
) -> pl.DataFrame:
    rows = []
    for record in raw:
        art_id = record.get("uuid")
        if not art_id:
            continue
        pub = record.get("published_at", "")
        effective_date = pub[:10] if pub else ""
        entities = record.get("entities") or []
        input_hash = _text_hash(record.get("title", ""), record.get("description", ""))
        for entity in entities:
            symbol = entity.get("symbol", "")
            ann_id = f"{source_id}_{art_id}_{symbol}" if symbol else f"{source_id}_{art_id}"
            rows.append(
                {
                    "annotation_id": ann_id,
                    "effective_date": effective_date,
                    "available_at": available_at,
                    "source_id": source_id,
                    "annotation_kind": "news_sentiment",
                    "sentiment_score": entity.get("sentiment_score"),
                    "sentiment_label": "",
                    "model_version": None,
                    "prompt_version": None,
                    "taxonomy_version": None,
                    "input_text_hash": input_hash,
                    "source_dataset_version": None,
                    "security_id": symbol,
                    **_meta(source_fetch_id, content_hash, ingestion_run_id),
                }
            )
    if not rows:
        return pl.DataFrame()
    df = pl.DataFrame(rows)
    return df.with_columns(
        pl.col("effective_date").str.to_date("%Y-%m-%d"),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
    )


def analyst_estimates_from_json(
    raw: list[dict[str, Any]],
    security_id: str,
    source_id: str,
    source_fetch_id: str,
    ingestion_run_id: str,
    content_hash: str,
    available_at: datetime,
) -> pl.DataFrame:
    rows = []
    for record in raw:
        period = record.get("period")
        if not period:
            continue
        rows.append(
            {
                "security_id": security_id,
                "effective_date": period,
                "available_at": available_at,
                "source_id": source_id,
                "strong_buy": int(record.get("strongBuy", 0)),
                "buy": int(record.get("buy", 0)),
                "hold": int(record.get("hold", 0)),
                "sell": int(record.get("sell", 0)),
                "strong_sell": int(record.get("strongSell", 0)),
                "target_mean": record.get("targetMean"),
                "target_high": record.get("targetHigh"),
                "target_low": record.get("targetLow"),
                **_meta(source_fetch_id, content_hash, ingestion_run_id),
            }
        )
    df = pl.DataFrame(rows)
    if df.is_empty():
        return pl.DataFrame()
    return df.with_columns(
        pl.col("effective_date").str.to_date("%Y-%m-%d"),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
    )


def earnings_calendar_from_json(
    raw: list[dict[str, Any]],
    source_id: str,
    source_fetch_id: str,
    ingestion_run_id: str,
    content_hash: str,
    available_at: datetime,
) -> pl.DataFrame:
    rows = []
    for record in raw:
        code = record.get("code", "")
        if not code:
            continue
        report_date_str = record.get("date", "")
        if not report_date_str:
            continue
        sid = code.split(".")[0] if "." in code else code
        time_raw = record.get("time", "")
        session = "regular"
        if "market" in time_raw.lower():
            session = "morning" if "before" in time_raw.lower() else "afternoon"
        rows.append(
            {
                "security_id": sid,
                "effective_date": report_date_str,
                "available_at": available_at,
                "source_id": source_id,
                "report_date": report_date_str,
                "session": session,
                **_meta(source_fetch_id, content_hash, ingestion_run_id),
            }
        )
    if not rows:
        return pl.DataFrame()
    df = pl.DataFrame(rows)
    return df.with_columns(
        pl.col("effective_date").str.to_date("%Y-%m-%d"),
        pl.col("report_date").str.to_date("%Y-%m-%d"),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
    )


def insider_tx_from_json(
    raw: list[dict[str, Any]],
    security_id: str,
    source_id: str,
    source_fetch_id: str,
    ingestion_run_id: str,
    content_hash: str,
    available_at: datetime,
) -> pl.DataFrame:
    rows = []
    for record in raw:
        year = record.get("year")
        month = record.get("month")
        if not year or not month:
            continue
        rows.append(
            {
                "security_id": security_id,
                "effective_date": f"{year}-{int(month):02d}-01",
                "available_at": available_at,
                "source_id": source_id,
                "filer_cik": "",
                "issuer_cik": "",
                "transaction_code": "P" if record.get("change", 0) >= 0 else "S",
                "shares": max(float(record.get("change", 0)), 0),
                "price": 0.0,
                "value": 0.0,
                **_meta(source_fetch_id, content_hash, ingestion_run_id),
            }
        )
    df = pl.DataFrame(rows)
    return df.with_columns(
        pl.col("effective_date").str.to_date("%Y-%m-%d"),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
    )


def stocktwits_sentiment_from_json(
    raw: list[dict[str, Any]],
    symbol: str,
    source_id: str,
    source_fetch_id: str,
    ingestion_run_id: str,
    content_hash: str,
    available_at: datetime,
) -> pl.DataFrame:
    rows = []
    for record in raw:
        msg_id = record.get("id")
        if not msg_id:
            continue
        sentiment_map = {"Bullish": 1.0, "Bearish": -1.0}
        sent = record.get("sentiment")
        sent_score = sentiment_map.get(sent, 0.0)
        body = record.get("body", "")
        created = (record.get("created_at") or "").replace("Z", "")
        rows.append(
            {
                "annotation_id": f"{source_id}_{msg_id}",
                "effective_date": created[:10] if created else "",
                "available_at": available_at,
                "source_id": source_id,
                "annotation_kind": "social_sentiment",
                "sentiment_score": sent_score,
                "sentiment_label": sent or "Neutral",
                "model_version": None,
                "prompt_version": None,
                "taxonomy_version": None,
                "input_text_hash": _text_hash(body),
                "source_dataset_version": None,
                "security_id": symbol,
                **_meta(source_fetch_id, content_hash, ingestion_run_id),
            }
        )
    if not rows:
        return pl.DataFrame()
    df = pl.DataFrame(rows)
    return df.with_columns(
        pl.col("effective_date").str.to_date("%Y-%m-%d"),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
    )


def apewisdom_attention_from_json(
    raw: list[dict[str, Any]],
    ticker: str,
    source_id: str,
    source_fetch_id: str,
    ingestion_run_id: str,
    content_hash: str,
    available_at: datetime,
    cohort: str = "all-stocks",
) -> pl.DataFrame:
    rows = []
    for record in raw:
        rows.append(
            {
                "security_id": ticker,
                "effective_date": available_at.strftime("%Y-%m-%d"),
                "available_at": available_at,
                "source_id": source_id,
                "cohort": cohort,
                "mentions": int(record.get("mentions", 0)),
                "mentions_24h_ago": int(record.get("mentions_24h_ago", 0)),
                "upvotes": record.get("upvotes"),
                "rank": record.get("rank"),
                "rank_24h_ago": record.get("rank_24h_ago"),
                "name": record.get("name") or None,
                **_meta(source_fetch_id, content_hash, ingestion_run_id),
                "parser_version": 2,
            }
        )
    if not rows:
        return pl.DataFrame()
    df = pl.DataFrame(rows)
    if df.is_empty():
        return pl.DataFrame()
    return df.with_columns(
        pl.col("effective_date").str.to_date("%Y-%m-%d"),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
    )


def earnings_calendar_from_finnhub(
    raw: list[dict[str, Any]],
    source_id: str,
    source_fetch_id: str,
    ingestion_run_id: str,
    content_hash: str,
    available_at: datetime,
) -> pl.DataFrame:
    # Finnhub wraps earnings in {"earningsCalendar": [...]}
    events: list[dict[str, Any]] = []
    for wrapper in raw:
        events.extend(wrapper.get("earningsCalendar") or [])
    rows: list[dict[str, Any]] = []
    for record in events:
        symbol = record.get("symbol", "")
        report_date_str = record.get("date", "")
        if not symbol or not report_date_str:
            continue
        hour = (record.get("hour") or "").lower()
        session = "regular"
        if hour in ("bmo", "am"):
            session = "morning"
        elif hour in ("dmh", "amc", "pm"):
            session = "afternoon"
        rows.append(
            {
                "security_id": symbol,
                "effective_date": report_date_str,
                "available_at": available_at,
                "source_id": source_id,
                "report_date": report_date_str,
                "session": session,
                **_meta(source_fetch_id, content_hash, ingestion_run_id),
            }
        )
    if not rows:
        return pl.DataFrame()
    df = pl.DataFrame(rows)
    return df.with_columns(
        pl.col("effective_date").str.to_date("%Y-%m-%d"),
        pl.col("report_date").str.to_date("%Y-%m-%d"),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
    )


def fundamentals_from_json(
    raw: list[dict[str, Any]],
    security_id: str,
    source_id: str,
    source_fetch_id: str,
    ingestion_run_id: str,
    content_hash: str,
    available_at: datetime,
) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    for record in raw:
        year = record.get("year")
        quarter = record.get("quarter")
        period_end = record.get("date", "")
        if not year or not quarter or not period_end:
            continue
        fiscal_period = f"FY{year}Q{quarter}"
        effective_date = period_end
        sd = record.get("statementData", {})
        stmt_map = {
            "incomeStatement": "income_statement",
            "balanceSheet": "balance_sheet",
            "cashFlow": "cash_flow",
            "overview": "overview",
        }
        for tiingo_key, stmt_type in stmt_map.items():
            items = sd.get(tiingo_key, [])
            if not items:
                continue
            for item in items:
                data_code = item.get("dataCode", "")
                value = item.get("value")
                if not data_code or value is None:
                    continue
                measure_kind = stmt_type
                rows.append(
                    {
                        "security_id": security_id,
                        "effective_date": effective_date,
                        "available_at": available_at,
                        "source_id": source_id,
                        "source_published_at": available_at,
                        "ingested_at": available_at,
                        "validated_at": None,
                        "fiscal_period": fiscal_period,
                        "period_kind": "quarterly",
                        "period_end": effective_date,
                        "measurement_kind": measure_kind,
                        "statement_type": stmt_type,
                        "line_item": data_code,
                        "value": float(value) if value else 0.0,
                        "currency": "USD",
                        "source_currency": "USD",
                        "unit": "raw",
                        "source_priority": None,
                        **_meta(source_fetch_id, content_hash, ingestion_run_id),
                    }
                )
    if not rows:
        return pl.DataFrame()
    df = pl.DataFrame(rows)
    return df.with_columns(
        pl.col("effective_date").str.to_date("%Y-%m-%d"),
        pl.col("period_end").str.to_date("%Y-%m-%d"),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("source_published_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("ingested_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("validated_at").cast(pl.Datetime(time_zone="UTC")),
    )


def _epoch_to_date(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, tz=UTC).strftime("%Y-%m-%d")


def _epoch_to_dt(epoch: int) -> datetime:
    return datetime.fromtimestamp(epoch, tz=UTC)


def _text_hash(*parts: str) -> str:
    return hashlib.sha256("".join(parts).encode()).hexdigest()


def _parse_iso_dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", ""))


def congress_trades_from_json(
    raw: list[dict[str, Any]],
    source_id: str,
    source_fetch_id: str,
    ingestion_run_id: str,
    content_hash: str,
    available_at: datetime,
) -> pl.DataFrame:
    """Normalize Quiver congress trades into CongressTradeFact rows."""
    rows: list[dict[str, Any]] = []
    for record in raw:
        tx_id = record.get("transaction_id") or record.get("id", "")
        ticker = record.get("ticker") or record.get("symbol", "")
        if not tx_id or not ticker:
            continue
        tx_date = record.get("transaction_date", "")
        rows.append(
            {
                "transaction_id": tx_id,
                "politician_id": record.get("politician") or record.get("politician_id", ""),
                "security_id": ticker,
                "effective_date": tx_date[:10] if tx_date else available_at.strftime("%Y-%m-%d"),
                "available_at": available_at,
                "source_id": source_id,
                "direction": str(record.get("type", record.get("direction", ""))).lower(),
                "amount_range": str(record.get("amount", record.get("amount_range", ""))),
                **_meta(source_fetch_id, content_hash, ingestion_run_id),
            }
        )
    if not rows:
        return pl.DataFrame()
    df = pl.DataFrame(rows)
    return df.with_columns(
        pl.col("effective_date").str.to_date("%Y-%m-%d"),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
    )


def social_posts_from_json(
    raw: list[dict[str, Any]],
    source_id: str,
    source_fetch_id: str,
    ingestion_run_id: str,
    content_hash: str,
    available_at: datetime,
    platform: str = "reddit",
) -> pl.DataFrame:
    """Normalize Reddit API posts into SocialPostFact rows.

    ``raw`` is a list containing one dict (the Reddit API response) with
    ``data.children`` containing the actual post objects.
    """
    import hashlib

    merged = raw[0] if raw else {}
    d = merged.get("data", {})
    children = d.get("children", []) if isinstance(d, dict) else []
    rows: list[dict[str, Any]] = []
    for child in children:
        post = child.get("data", {}) if isinstance(child, dict) else {}
        post_id = post.get("id", "")
        if not post_id:
            continue
        title = post.get("title", "")
        selftext = post.get("selftext", "")
        text_hash = hashlib.sha256((title + selftext).encode()).hexdigest()
        created_utc = post.get("created_utc", 0)
        published = datetime.fromtimestamp(created_utc, tz=UTC) if created_utc else available_at
        rows.append(
            {
                "post_id_hash": hashlib.sha256(post_id.encode()).hexdigest(),
                "effective_date": published.strftime("%Y-%m-%d"),
                "available_at": available_at,
                "source_id": source_id,
                "platform": platform,
                "venue": post.get("subreddit", ""),
                "parent_id_hash": None,
                "text_hash": text_hash,
                "published_at": published,
                "engagement_json": json.dumps(
                    {"ups": post.get("ups", 0), "comments": post.get("num_comments", 0)}
                ),
                **_meta(source_fetch_id, content_hash, ingestion_run_id),
            }
        )
    if not rows:
        return pl.DataFrame()
    df = pl.DataFrame(rows)
    return df.with_columns(
        pl.col("effective_date").str.to_date("%Y-%m-%d"),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("published_at").cast(pl.Datetime(time_zone="UTC")),
    )
