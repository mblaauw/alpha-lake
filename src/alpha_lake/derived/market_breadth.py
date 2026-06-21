from __future__ import annotations

from datetime import datetime

import polars as pl

from alpha_lake.canonical import compute_version_hash
from alpha_lake.derived.indicators import sma


def compute_market_breadth(
    bars: pl.DataFrame,
    as_of: datetime,
    basket_ids: list[str] | None = None,
    sector_ids: list[str] | None = None,
    ratio_pairs: list[tuple[str, str, str]] | None = None,
) -> pl.DataFrame:
    """Compute market-breadth measurements from OHLCV bars.

    For each ``effective_date`` in ``bars``, computes:

    - ``pct_above_50ma``, ``pct_above_200ma`` — % of ``basket_ids`` above
      their simple moving average.
    - ``sector_{name}_pct_above_50ma``, ``sector_{name}_pct_above_200ma`` —
      same for each sector ETF list.
    - ``ratio_{name}`` — close ratio of numerator/denominator from
      ``ratio_pairs``.

    Returns a ``pl.DataFrame`` with one row per ``(metric_id, effective_date)``.
    """
    sorted_bars = bars.sort("security_id", "effective_date")
    unique_dates = sorted_bars["effective_date"].unique().sort()
    rows: list[dict] = []

    for dt in unique_dates:
        avail = sorted_bars.filter(pl.col("effective_date") == dt)["available_at"].max()
        if avail is None:
            continue
        _compute_ma_pct(sorted_bars, dt, basket_ids or [], "pct_above", rows, as_of)
        for sector_name, sec_ids in _group_sectors(sector_ids or []):
            mid = f"sector_{sector_name}_pct_above"
            _compute_ma_pct(sorted_bars, dt, sec_ids, mid, rows, as_of)
        _compute_ratios(sorted_bars, dt, ratio_pairs or [], rows, as_of)

    df = pl.DataFrame(rows)
    if df.is_empty():
        return df
    df = compute_version_hash(df)
    return df.with_columns(
        pl.col("effective_date").cast(pl.Date),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
    )


def _above_pct(bars: pl.DataFrame, ids: list[str], window: int, dt) -> float | None:
    """Percentage of ``ids`` whose close is above their *window*-MA at ``dt``."""
    if not ids:
        return None
    above = 0
    total = 0
    for sid in ids:
        s = bars.filter(pl.col("security_id") == sid).sort("effective_date")
        if s.is_empty():
            continue
        bars_before = s.filter(pl.col("effective_date") <= dt)
        if len(bars_before) < window:
            continue
        total += 1
        close = bars_before["close"]
        ma = sma(close, window)
        if len(ma) > 0 and close[-1] > ma[-1]:
            above += 1
    return (above / total * 100) if total > 0 else None


def _compute_ma_pct(
    bars: pl.DataFrame,
    dt,
    ids: list[str],
    metric_prefix: str,
    rows: list[dict],
    as_of: datetime,
) -> None:
    for window, label in ((50, "50ma"), (200, "200ma")):
        val = _above_pct(bars, ids, window, dt)
        if val is not None:
            rows.append(
                {
                    "metric_id": f"{metric_prefix}_{label}",
                    "effective_date": dt,
                    "available_at": as_of,
                    "value": val,
                    "source_id": "derived",
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


def _group_sectors(sector_ids: list[str]) -> list[tuple[str, list[str]]]:
    return [("all", sector_ids)]


def _compute_ratios(
    bars: pl.DataFrame,
    dt,
    pairs: list[tuple[str, str, str]],
    rows: list[dict],
    as_of: datetime,
) -> None:
    for name, num_id, den_id in pairs:
        num_close = _close_at_date(bars, num_id, dt)
        den_close = _close_at_date(bars, den_id, dt)
        ratio = (num_close / den_close) if (num_close and den_close) else None
        rows.append(
            {
                "metric_id": f"ratio_{name}",
                "effective_date": dt,
                "available_at": as_of,
                "value": ratio,
                "source_id": "derived",
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


def _close_at_date(bars: pl.DataFrame, sid: str, dt) -> float | None:
    s = bars.filter(pl.col("security_id") == sid, pl.col("effective_date") == dt)
    if s.is_empty():
        return None
    return s["close"][0]
