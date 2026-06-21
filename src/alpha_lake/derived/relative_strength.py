from __future__ import annotations

from datetime import datetime

import polars as pl

from alpha_lake.canonical import compute_version_hash
from alpha_lake.derived.indicators import returns

_RS_WINDOWS = (1, 5, 21, 63, 126, 252)


def compute_relative_strength(
    bars: pl.DataFrame,
    benchmark_bars: pl.DataFrame,
    as_of: datetime,
    universe_ids: list[str] | None = None,
) -> pl.DataFrame:
    """Compute per-symbol relative-strength returns vs a benchmark.

    ``bars`` must contain ``security_id``, ``effective_date``, ``close``,
    ``available_at`` sorted by ``(security_id, effective_date)``.

    Returns one row per ``(security_id, effective_date, window)`` with the
    return difference and its cross-sectional percentile.
    """
    benchmark_close = benchmark_bars.sort("effective_date")["close"]
    rows: list[dict] = []

    for sid in bars["security_id"].unique():
        symbol_bars = bars.filter(pl.col("security_id") == sid).sort("effective_date")
        close = symbol_bars["close"]
        avail = symbol_bars["available_at"].max()
        if avail is None:
            continue

        for window in _RS_WINDOWS:
            sym_ret = returns(close, window)
            bmk_ret = returns(benchmark_close, window)
            rs = sym_ret - bmk_ret

            for i in range(len(symbol_bars)):
                val = rs[i]
                if val is None:
                    continue
                rows.append(
                    {
                        "security_id": sid,
                        "effective_date": symbol_bars["effective_date"][i],
                        "available_at": as_of,
                        "window": window,
                        "source_id": "derived",
                        "rs_return": val,
                        "rs_percentile": None,
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

    if universe_ids is not None and len(bars["security_id"].unique()) > 1:
        df = df.with_columns(
            pl.col("rs_return")
            .rank("average", descending=True)
            .over("effective_date", "window")
            .alias("_rank")
        )
        df = df.with_columns(
            ((pl.col("_rank") - 1) / pl.count("_rank").over("effective_date", "window") * 100)
            .fill_null(50.0)
            .alias("rs_percentile")
        ).drop("_rank")

    return df.with_columns(
        pl.col("effective_date").cast(pl.Date),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
    )
