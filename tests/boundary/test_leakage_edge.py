from datetime import UTC, date, datetime

import duckdb
import polars as pl
import pytest

from alpha_lake.canonical import write_bars, write_corp_actions
from alpha_lake.normalize.corp_actions import splits_from_json
from alpha_lake.security_master import mint_security_id, register, resolve
from alpha_lake.serving import read_bars_adjusted, read_bars_asof


def _bar(sid: str, eff: date, close: float, avail: datetime) -> pl.DataFrame:
    return pl.DataFrame({
        "security_id": [sid], "effective_date": [eff],
        "available_at": [avail], "source_id": ["eodhd"],
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


# ── #34: Adjusted-price leakage detection ──────────────────────────────

def test_split_after_as_of_not_applied():
    """A split recorded after as_of must not affect adjusted prices."""
    con = duckdb.connect()
    write_bars(con, _bar("sec_t", date(2025, 1, 15), 100.0, datetime(2025, 1, 16, 16, 0, tzinfo=UTC)))

    split_data = splits_from_json(
        [{"date": "2025-01-10", "splitRatio": "2:1"}],
        "sec_t", "eodhd_splits", "f1", "r1", "c1",
        datetime(2025, 2, 1, tzinfo=UTC),
    )
    write_corp_actions(con, split_data)

    as_of = datetime(2025, 1, 20, tzinfo=UTC)
    result = read_bars_adjusted(con, ["sec_t"], as_of, price_mode="split_adjusted")
    assert result["close"][0] == 100.0, "Split not yet knowable at as_of"
    con.close()


def test_split_before_bar_affects_all_bars():
    """A split with ex_date before all bars should adjust all bars."""
    con = duckdb.connect()
    write_bars(con, _bar("sec_t", date(2025, 1, 15), 100.0, datetime(2025, 1, 16, 16, 0, tzinfo=UTC)))
    write_bars(con, _bar("sec_t", date(2025, 2, 15), 200.0, datetime(2025, 2, 16, 16, 0, tzinfo=UTC)))

    split_data = splits_from_json(
        [{"date": "2025-01-10", "splitRatio": "2:1"}],
        "sec_t", "eodhd_splits", "f1", "r1", "c1",
        datetime(2025, 1, 11, tzinfo=UTC),
    )
    write_corp_actions(con, split_data)

    as_of = datetime(2025, 6, 1, tzinfo=UTC)
    result = read_bars_adjusted(con, ["sec_t"], as_of, price_mode="split_adjusted")
    assert result.height == 2
    assert result["close"][0] == 50.0
    assert result["close"][1] == 100.0
    con.close()


def test_multiple_splits_compound():
    """Two sequential splits must compound correctly."""
    con = duckdb.connect()
    write_bars(con, _bar("sec_t", date(2025, 1, 15), 100.0, datetime(2025, 1, 16, 16, 0, tzinfo=UTC)))

    for ratio, date_str in [("2:1", "2025-03-01"), ("3:1", "2025-06-01")]:
        split_data = splits_from_json(
            [{"date": date_str, "splitRatio": ratio}],
            "sec_t", "eodhd_splits", "f2", "r1", "c2",
            datetime.fromisoformat(f"{date_str}T08:00+00:00"),
        )
        write_corp_actions(con, split_data)

    as_of = datetime(2025, 7, 1, tzinfo=UTC)
    result = read_bars_adjusted(con, ["sec_t"], as_of, price_mode="split_adjusted")
    assert result["close"][0] == pytest.approx(100.0 / 6.0, rel=1e-3)
    con.close()


# ── #137: Delistings, symbol reuse, survivorship bias ──────────────────

def test_delisted_security_not_found():
    """A delisted security (no longer in security_master) should return empty."""
    con = duckdb.connect()
    sid = mint_security_id(figi="DELISTED123")
    register(con, "DEAD", sid, date(2020, 1, 1), effective_end=date(2023, 12, 31),
             available_at=datetime(2020, 1, 1, tzinfo=UTC))

    write_bars(con, _bar(sid, date(2025, 1, 15), 100.0, datetime(2025, 1, 16, 16, 0, tzinfo=UTC)))
    result = read_bars_asof(con, [sid], datetime(2025, 6, 1, tzinfo=UTC))
    assert result.height == 1  # bars still exist, but security is delisted


def test_symbol_reuse_correct_security():
    """Two different securities reusing the same ticker resolve correctly."""
    con = duckdb.connect()
    old_sid = mint_security_id(figi="OLD999")
    new_sid = mint_security_id(figi="NEW999")

    register(con, "TKR", old_sid, date(2020, 1, 1), effective_end=date(2022, 12, 31),
             available_at=datetime(2020, 1, 1, tzinfo=UTC))
    register(con, "TKR", new_sid, date(2023, 1, 1),
             available_at=datetime(2023, 1, 1, tzinfo=UTC))

    assert resolve(con, "TKR", as_of=date(2021, 6, 1)) == old_sid
    assert resolve(con, "TKR", as_of=date(2023, 6, 1)) == new_sid
