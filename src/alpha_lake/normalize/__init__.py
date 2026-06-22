from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

import polars as pl


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
                "source_fetch_id": source_fetch_id,
                "raw_payload_hash": content_hash,
                "ingestion_run_id": ingestion_run_id,
                "content_hash": content_hash,
                "version_hash": "",
                "schema_version": 1,
                "parser_version": 1,
                "quality_status": "valid",
            }
        )

    df = pl.DataFrame(rows)
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
                "source_fetch_id": source_fetch_id,
                "raw_payload_hash": content_hash,
                "ingestion_run_id": ingestion_run_id,
                "content_hash": content_hash,
                "version_hash": "",
                "schema_version": 1,
                "parser_version": 1,
                "quality_status": "valid",
            }
        )

    df = pl.DataFrame(rows)
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
                "source_fetch_id": source_fetch_id,
                "raw_payload_hash": content_hash,
                "ingestion_run_id": ingestion_run_id,
                "content_hash": content_hash,
                "version_hash": "",
                "schema_version": 1,
                "parser_version": 1,
                "quality_status": "valid",
            }
        )

    df = pl.DataFrame(rows)
    return df.with_columns(
        pl.col("effective_date").str.to_date("%Y-%m-%d"),
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
                "source_fetch_id": source_fetch_id,
                "raw_payload_hash": content_hash,
                "ingestion_run_id": ingestion_run_id,
                "content_hash": content_hash,
                "version_hash": "",
                "schema_version": 1,
                "parser_version": 1,
                "quality_status": "valid",
            }
        )
    df = pl.DataFrame(rows)
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
                "source_fetch_id": source_fetch_id,
                "raw_payload_hash": content_hash,
                "ingestion_run_id": ingestion_run_id,
                "content_hash": content_hash,
                "version_hash": "",
                "schema_version": 1,
                "parser_version": 1,
                "quality_status": "valid",
            }
        )
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
                "source_fetch_id": source_fetch_id,
                "raw_payload_hash": content_hash,
                "ingestion_run_id": ingestion_run_id,
                "content_hash": content_hash,
                "version_hash": "",
                "schema_version": 1,
                "parser_version": 1,
                "quality_status": "valid",
            }
        )
    df = pl.DataFrame(rows)
    return df.with_columns(
        pl.col("effective_date").str.to_date("%Y-%m-%d"),
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
                "source_fetch_id": source_fetch_id,
                "raw_payload_hash": content_hash,
                "ingestion_run_id": ingestion_run_id,
                "content_hash": content_hash,
                "version_hash": "",
                "schema_version": 1,
                "parser_version": 1,
                "quality_status": "valid",
            }
        )
    df = pl.DataFrame(rows)
    return df.with_columns(
        pl.col("effective_date").str.to_date("%Y-%m-%d"),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
    )


def _epoch_to_date(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, tz=UTC).strftime("%Y-%m-%d")


def _epoch_to_dt(epoch: int) -> datetime:
    return datetime.fromtimestamp(epoch, tz=UTC)


def _text_hash(*parts: str) -> str:
    return hashlib.sha256("".join(parts).encode()).hexdigest()
