from __future__ import annotations

from datetime import datetime

import polars as pl

from alpha_lake.canonical import compute_version_hash


def compute_macro_transforms(
    macro_data: pl.DataFrame,
    as_of: datetime,
) -> pl.DataFrame:
    """Compute YoY and MoM transforms from macro series vintages.

    ``macro_data`` must contain ``series_id``, ``effective_date``,
    ``available_at``, ``value``, ``source_id``, and all lineage columns.

    For each ``(series_id, effective_date, available_at)``, computes:
    - ``{series_id}_YOY``: (value / value 12mo ago) - 1
    - ``{series_id}_MOM``: (value / value 1mo ago) - 1

    Both use only observations where ``available_at <= as_of``
    to respect the knowledge-time bound.
    """
    sorted_data = macro_data.sort("series_id", "effective_date", "available_at")

    pit_data = sorted_data.filter(pl.col("available_at") <= as_of)

    rows: list[dict] = []
    for series_id in pit_data["series_id"].unique():
        s = pit_data.filter(pl.col("series_id") == series_id).sort("effective_date", "available_at")

        values_by_date: dict[str, float] = {}
        for row in s.iter_rows(named=True):
            ed_str = str(row["effective_date"])
            if ed_str not in values_by_date or row["available_at"] > values_by_date.get("_avail"):
                values_by_date[ed_str] = row["value"]
                values_by_date[f"_{ed_str}_avail"] = row["available_at"]

        sorted_date_strs = sorted(d for d in values_by_date if not d.startswith("_"))

        for _i, ed_str in enumerate(sorted_date_strs):
            val = values_by_date[ed_str]
            ed_obj = __import__("datetime").date.fromisoformat(ed_str) if ed_str else None
            if ed_obj is not None:
                matches = s.filter(pl.col("effective_date") == ed_obj)
                source_id = matches["source_id"][0] if not matches.is_empty() else "fred"
            else:
                source_id = "fred"

            for _transform, shift_fn, label in [
                ("YOY", _date_shift_yearly, lambda _e, s: f"{s}_YOY"),
                ("MOM", _date_shift_monthly, lambda _e, s: f"{s}_MOM"),
            ]:
                prev_date = shift_fn(ed_str)
                if prev_date in values_by_date:
                    prev_val = values_by_date[prev_date]
                    if prev_val is not None and prev_val != 0:
                        tf_val = (val / prev_val) - 1
                    else:
                        continue
                else:
                    continue

                rows.append(
                    {
                        "series_id": label(ed_str, series_id),
                        "effective_date": ed_str,
                        "available_at": as_of,
                        "source_id": source_id,
                        "value": tf_val,
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


def _date_shift_yearly(iso_date: str) -> str:
    try:
        parts = iso_date.split("-")
        year = int(parts[0]) - 1
        return f"{year}-{parts[1]}-{parts[2]}"
    except (IndexError, ValueError):
        return ""


def _prev_month(iso_date: str) -> str:
    try:
        parts = iso_date.split("-")
        year = int(parts[0])
        month = int(parts[1]) - 1
        if month == 0:
            year -= 1
            month = 12
        return f"{year}-{month:02d}-{parts[2]}"
    except (IndexError, ValueError):
        return ""


def _date_shift_monthly(iso_date: str) -> str:
    try:
        parts = iso_date.split("-")
        year = int(parts[0])
        month = int(parts[1]) - 1
        if month == 0:
            year -= 1
            month = 12
        return f"{year}-{month:02d}-{parts[2]}"
    except (IndexError, ValueError):
        return ""
