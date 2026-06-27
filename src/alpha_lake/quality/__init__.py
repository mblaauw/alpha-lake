from __future__ import annotations

import polars as pl


def check_market_sanity(df: pl.DataFrame) -> pl.DataFrame:
    condition = (
        (pl.col("low") <= pl.col("open"))
        & (pl.col("low") <= pl.col("close"))
        & (pl.col("open") <= pl.col("high"))
        & (pl.col("close") <= pl.col("high"))
        & (pl.col("volume") >= 0)
        & (pl.col("open") >= 0)
    )
    return df.with_columns(
        pl.when(condition)
        .then(pl.col("quality_status"))
        .otherwise(pl.lit("quarantined"))
        .alias("quality_status")
    )
