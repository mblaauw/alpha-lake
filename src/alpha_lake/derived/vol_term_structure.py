from __future__ import annotations

from datetime import datetime

import polars as pl

from alpha_lake.canonical import compute_version_hash

# Volatility index series IDs expected in the input bars data.
# These are the standard CBOE tickers for the vol term structure.
VOL_SERIES = {
    "spot": "VIX",  # VIX 30-day
    "front": "VIX9D",  # VIX 9-day
    "mid": "VIX3M",  # VIX 3-month
    "back": "VIX6M",  # VIX 6-month
}


def compute_vol_term_structure(
    bars: pl.DataFrame,
    as_of: datetime,
) -> pl.DataFrame:
    """Compute vol-index levels and derived term-structure spreads.

    ``bars`` must contain ``security_id``, ``effective_date``, ``close``,
    ``available_at`` sorted by ``(security_id, effective_date)``.

    Expected security_id values match the ``VOL_SERIES`` map keys
    (``VIX``, ``VIX9D``, ``VIX3M``, ``VIX6M``).

    Returns a ``pl.DataFrame`` with one row per ``(series_id, effective_date)``
    containing the level, plus derived ``contango_spread`` rows.
    """
    sorted_bars = bars.sort("security_id", "effective_date")
    unique_dates = sorted_bars["effective_date"].unique().sort()
    rows: list[dict] = []
    source_id = "derived"

    for dt in unique_dates:
        avail = sorted_bars.filter(pl.col("effective_date") == dt)["available_at"].max()
        if avail is None:
            continue

        levels: dict[str, float | None] = {}
        for label, sid in VOL_SERIES.items():
            s = sorted_bars.filter(pl.col("security_id") == sid, pl.col("effective_date") == dt)
            levels[label] = s["close"][0] if not s.is_empty() else None

        for label, sid in VOL_SERIES.items():
            val = levels[label]
            rows.append(
                {
                    "series_id": sid,
                    "effective_date": dt,
                    "available_at": as_of,
                    "source_id": source_id,
                    "value": val,
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

        spot = levels.get("spot")
        front = levels.get("front")
        mid = levels.get("mid")

        if spot is not None and mid is not None:
            rows.append(
                {
                    "series_id": "contango_3m_spot",
                    "effective_date": dt,
                    "available_at": as_of,
                    "source_id": source_id,
                    "value": mid - spot,
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

        if spot is not None and front is not None and spot != 0:
            rows.append(
                {
                    "series_id": "contango_front_ratio",
                    "effective_date": dt,
                    "available_at": as_of,
                    "source_id": source_id,
                    "value": front / spot,
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
