"""Smoke tests — verify core modules import without error."""

from datetime import UTC


def test_cli_imports():
    from alpha_lake.cli import app

    assert app.info.name == "alpha-lake"


def test_config_imports():
    from alpha_lake.config import RootConfig, load_config

    assert RootConfig is not None
    assert load_config is not None


def test_obs_imports():
    from alpha_lake.obs import setup_otel

    assert setup_otel is not None


def test_source_registry():
    from alpha_lake.source_registry import get_source_precedence

    assert get_source_precedence("bars_daily") == ["eodhd", "tiingo"]


def test_config_reconcile():
    from alpha_lake.config import ReconciliationConfig

    cfg = ReconciliationConfig(price_diff_pct=0.5)
    assert cfg.price_diff_pct == 0.5
    assert cfg.volume_diff_pct == 5.0


def test_pit_reader_imports():
    from alpha_lake.serving import read_bars_asof, read_bars_latest

    assert read_bars_asof is not None
    assert read_bars_latest is not None


def test_quality_market_sanity():
    from datetime import date

    import polars as pl

    from alpha_lake.quality import check_market_sanity

    df = pl.DataFrame(
        {
            "security_id": ["sec_ok", "sec_bad"],
            "effective_date": [date(2026, 6, 18), date(2026, 6, 18)],
            "open": [100.0, 50.0],
            "high": [101.0, 100.0],
            "low": [99.0, 60.0],
            "close": [100.5, 55.0],
            "volume": [10000, 5000],
            "quality_status": ["valid", "valid"],
        }
    )
    result = check_market_sanity(df)
    assert result["quality_status"][0] == "valid"
    assert result["quality_status"][1] == "quarantined"


def test_canonical_write_bars():
    from datetime import date, datetime

    import duckdb
    import polars as pl

    from alpha_lake.canonical import write_bars

    con = duckdb.connect()
    df = pl.DataFrame(
        {
            "security_id": ["sec_test"],
            "effective_date": [date(2026, 6, 18)],
            "available_at": [datetime(2026, 6, 18, 12, 0, 0)],
            "source_id": ["eodhd"],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [10000],
            "source_fetch_id": [""],
            "raw_payload_hash": [""],
            "ingestion_run_id": [""],
            "content_hash": [""],
            "version_hash": [""],
            "schema_version": [1],
            "parser_version": [1],
            "quality_status": ["valid"],
            "source_published_at": [None],
            "ingested_at": [None],
            "validated_at": [None],
        }
    ).with_columns(
        pl.col("source_published_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("ingested_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("validated_at").cast(pl.Datetime(time_zone="UTC")),
    )
    count = write_bars(con, df)
    assert count == 1
    con.close()


def test_bar_fact():
    from datetime import date, datetime

    import polars as pl

    from alpha_lake.models.bar_fact import BarFact

    df = pl.DataFrame(
        {
            "security_id": ["sec_test"],
            "effective_date": [date(2026, 6, 18)],
            "available_at": [datetime(2026, 6, 18, 12, 0, 0)],
            "source_id": ["eodhd"],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [10000],
            "source_fetch_id": [""],
            "raw_payload_hash": [""],
            "ingestion_run_id": [""],
            "content_hash": [""],
            "version_hash": [""],
            "schema_version": [1],
            "parser_version": [1],
            "quality_status": ["valid"],
            "source_published_at": [None],
            "ingested_at": [None],
            "validated_at": [None],
        }
    ).with_columns(
        pl.col("source_published_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("ingested_at").cast(pl.Datetime(time_zone="UTC")),
        pl.col("validated_at").cast(pl.Datetime(time_zone="UTC")),
    )
    validated = BarFact.validate(df)
    assert validated.height == 1


def test_normalize_bars():
    from datetime import datetime

    from alpha_lake.normalize import bars_from_json

    ts = datetime(2026, 6, 18, 12, 0, 0, tzinfo=UTC)
    raw = [
        {
            "date": "2026-06-18",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 10000,
        }
    ]
    df = bars_from_json(raw, "sec_test", "eodhd", "fetch_1", "run_1", "abc123", ts)
    assert df.shape == (1, 20)
    assert df["close"][0] == 100.5


def test_raw_archive():
    from alpha_lake.config import load_config
    from alpha_lake.raw import archive, read_raw

    load_config("config/embedded.toml")
    h = archive(b"test data")
    assert read_raw(h) == b"test data"


def test_calendar_imports():
    from datetime import date

    from alpha_lake.calendar_ import is_trading_day, previous_trading_day

    assert is_trading_day(date(2026, 6, 18)) is True
    assert previous_trading_day(date(2026, 6, 19)) == date(2026, 6, 18)
