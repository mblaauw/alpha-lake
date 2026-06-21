from datetime import UTC, date, datetime

import duckdb
import polars as pl
import pytest

from alpha_lake.canonical import write_bars, write_corp_actions
from alpha_lake.normalize.corp_actions import splits_from_json
from alpha_lake.serving import read_bars_adjusted


def _bar(close: float, avail: str) -> pl.DataFrame:
    ts = datetime.fromisoformat(avail)
    eff = date(2026, 1, 5)
    return pl.DataFrame({
        "security_id": ["sec_lk"], "effective_date": [eff],
        "available_at": [ts], "source_id": ["eodhd"],
        "open": [close], "high": [close * 1.01], "low": [close * 0.99],
        "close": [close], "volume": [10000],
        "source_fetch_id": [""], "raw_payload_hash": [""],
        "ingestion_run_id": [""], "content_hash": [""], "version_hash": [""],
        "schema_version": [1], "parser_version": [1], "quality_status": ["valid"],
        "source_published_at": [None], "ingested_at": [None], "validated_at": [None],
    }).with_columns(
        pl.col("source_published_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("ingested_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("validated_at").cast(pl.Datetime(time_zone="UTC")),
    )


@pytest.fixture
def con():
    c = duckdb.connect()
    c.execute("SET timezone = 'UTC'")
    yield c
    c.close()


def test_raw_price_unaffected_by_future_adjustment(con):
    """Split recorded after as_of must not affect adjusted price."""
    write_bars(con, _bar(100.0, "2026-01-05T16:00:00+00:00"))
    split = splits_from_json(
        [{"date": "2026-01-01", "splitRatio": "2:1"}],
        "sec_lk", "eodhd_splits", "f1", "r1", "c1",
        datetime(2026, 1, 10, 8, 0, tzinfo=UTC),
    )
    write_corp_actions(con, split)

    result = read_bars_adjusted(con, ["sec_lk"],
        datetime(2026, 1, 8, 12, 0, tzinfo=UTC), price_mode="split_adjusted")
    assert result["close"][0] == 100.0, "split not yet knowable"


def test_adjustment_applied_when_knowable(con):
    """Split with available_at <= as_of must be applied."""
    write_bars(con, _bar(100.0, "2026-01-05T16:00:00+00:00"))
    split = splits_from_json(
        [{"date": "2026-01-01", "splitRatio": "2:1"}],
        "sec_lk", "eodhd_splits", "f1", "r1", "c1",
        datetime(2026, 1, 8, 8, 0, tzinfo=UTC),
    )
    write_corp_actions(con, split)

    result = read_bars_adjusted(con, ["sec_lk"],
        datetime(2026, 1, 10, 12, 0, tzinfo=UTC), price_mode="split_adjusted")
    assert result["close"][0] == 50.0, "split should be applied"


def test_multiple_adjustment_sources_respect_visibility(con):
    """Two splits at different available_ats must apply independently."""
    write_bars(con, _bar(100.0, "2026-01-05T16:00:00+00:00"))

    s1 = splits_from_json([{"date": "2026-01-01", "splitRatio": "2:1"}],
        "sec_lk", "eodhd_splits", "f1", "r1", "c1",
        datetime(2026, 1, 8, 8, 0, tzinfo=UTC))
    write_corp_actions(con, s1)

    s2 = splits_from_json([{"date": "2026-01-15", "splitRatio": "3:1"}],
        "sec_lk", "eodhd_splits", "f2", "r1", "c2",
        datetime(2026, 1, 20, 8, 0, tzinfo=UTC))
    write_corp_actions(con, s2)

    early = read_bars_adjusted(con, ["sec_lk"],
        datetime(2026, 1, 10, 12, 0, tzinfo=UTC), price_mode="split_adjusted")
    assert early["close"][0] == 50.0, "only first split visible"

    late = read_bars_adjusted(con, ["sec_lk"],
        datetime(2026, 2, 1, 12, 0, tzinfo=UTC), price_mode="split_adjusted")
    assert late["close"][0] == pytest.approx(100.0 / 6.0, rel=1e-3), "both splits visible"
