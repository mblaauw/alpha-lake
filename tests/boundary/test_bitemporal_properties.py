from datetime import date, datetime, timezone

import duckdb
import polars as pl
from hypothesis import given, settings, strategies as st

from alpha_lake.canonical import write_bars
from alpha_lake.serving import read_bars_asof


def _row(security_id: str, effective: date, avail: datetime, close: float) -> pl.DataFrame:
    return pl.DataFrame({
        "security_id": [security_id],
        "effective_date": [effective],
        "available_at": [avail],
        "source_id": ["eodhd"],
        "open": [close * 0.99], "high": [close * 1.01], "low": [close * 0.98],
        "close": [close], "volume": [100000],
        "source_fetch_id": [""], "raw_payload_hash": [""],
        "ingestion_run_id": [""], "content_hash": [""], "version_hash": [""],
        "schema_version": [1], "parser_version": [1], "quality_status": ["valid"],
        "source_published_at": [None], "ingested_at": [None], "validated_at": [None],
    }).with_columns(
        pl.col("source_published_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("ingested_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("validated_at").cast(pl.Datetime(time_zone="UTC")),
    )


_ids = st.text(min_size=1, max_size=10).filter(lambda s: s.isascii())


@given(security_id=_ids, effective=st.dates(min_value=date(2020, 1, 1), max_value=date(2025, 5, 31)))
@settings(deadline=None)
def test_never_leak(security_id: str, effective: date):
    """Every returned row must have available_at <= as_of (invariant I5)."""
    con = duckdb.connect()
    as_of = datetime(2025, 6, 15, 12, 0, tzinfo=timezone.utc)
    write_bars(con, _row(security_id, effective, datetime(2025, 6, 1, 16, 0, tzinfo=timezone.utc), 100.0))
    result = read_bars_asof(con, [security_id], as_of)
    for row in result.iter_rows(named=True):
        assert row["available_at"] <= as_of, f"Leak: available_at={row['available_at']} > as_of={as_of}"
    con.close()


@given(security_id=_ids, effective=st.dates(min_value=date(2020, 1, 1), max_value=date(2025, 5, 31)))
@settings(deadline=None)
def test_restatement_immutable(security_id: str, effective: date):
    """A later restatement must not change what an earlier as_of sees."""
    con = duckdb.connect()
    t1 = datetime(2025, 6, 1, 16, 0, tzinfo=timezone.utc)
    t2 = datetime(2025, 6, 3, 8, 0, tzinfo=timezone.utc)
    as_of_early = datetime(2025, 6, 2, 12, 0, tzinfo=timezone.utc)

    write_bars(con, _row(security_id, effective, t1, 100.0))
    before = read_bars_asof(con, [security_id], as_of_early)
    assert before.height == 1
    assert before["close"][0] == 100.0

    write_bars(con, _row(security_id, effective, t2, 200.0))
    after = read_bars_asof(con, [security_id], as_of_early)
    assert after.height == 1
    assert after["close"][0] == 100.0, "Restatement mutated prior version"
    con.close()


@given(security_id=_ids, effective=st.dates(min_value=date(2020, 1, 1), max_value=date(2025, 6, 14)))
@settings(deadline=None)
def test_backfill_visibility(security_id: str, effective: date):
    """A backfill must be invisible to as_of before its available_at."""
    con = duckdb.connect()
    write_bars(con, _row(security_id, effective, datetime(2025, 6, 10, 16, 0, tzinfo=timezone.utc), 100.0))

    early = read_bars_asof(con, [security_id], datetime(2025, 6, 5, 12, 0, tzinfo=timezone.utc))
    assert early.height == 0, "Backfill leaked into earlier as_of"

    late = read_bars_asof(con, [security_id], datetime(2025, 6, 15, 12, 0, tzinfo=timezone.utc))
    assert late.height == 1, "Backfill not visible at later as_of"
    con.close()
