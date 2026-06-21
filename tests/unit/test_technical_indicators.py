from __future__ import annotations

from datetime import UTC, datetime

import polars as pl
import pytest

from alpha_lake.canonical import DATASETS
from alpha_lake.derived.indicators import (
    above_ma,
    atr_pct,
    avg_dollar_volume,
    distance_to_ma,
    dollar_volume,
    gap_pct,
    is_new_high,
    is_new_low,
    macd,
    pct_off_high,
    pct_off_low,
    realized_vol,
    relative_volume,
    returns,
    rsi,
    sma,
)
from alpha_lake.models.technical_fact import TechnicalIndicatorFact


def _sample_series(n: int = 100) -> pl.Series:
    return pl.Series(range(1, n + 1), dtype=pl.Float64)


# --- Model & registry ---


def test_technical_fact_valid():
    row: dict[str, object] = {
        "security_id": "sec_abc",
        "effective_date": "2024-01-15",
        "available_at": datetime(2024, 1, 16, tzinfo=UTC),
        "source_id": "eodhd",
        "source_fetch_id": "",
        "raw_payload_hash": "",
        "ingestion_run_id": "",
        "content_hash": "",
        "version_hash": "",
        "schema_version": 1,
        "parser_version": 1,
        "quality_status": "valid",
    }
    for c in TechnicalIndicatorFact.model_fields:
        if c not in row:
            ann = str(TechnicalIndicatorFact.model_fields[c].annotation)
            if "bool" in ann.lower():
                row[c] = False
            else:
                row[c] = 0.0
    df = pl.DataFrame({k: [v] for k, v in row.items()}).with_columns(
        pl.col("effective_date").str.to_date("%Y-%m-%d"),
        pl.col("available_at").cast(pl.Datetime(time_zone="UTC")),
    )
    validated = TechnicalIndicatorFact.validate(df)
    assert len(validated) == 1


def test_technical_indicators_registered():
    assert "technical_indicators" in DATASETS
    ds = DATASETS["technical_indicators"]
    assert ds.model is TechnicalIndicatorFact
    assert "security_id" in ds.natural_keys


# --- Returns ---


def test_returns_identity():
    s = _sample_series(10)
    r = returns(s, 1)
    assert r[1] == pytest.approx((2 / 1) - 1)
    assert r[0] is None


def test_returns_warmup_is_null():
    s = _sample_series(10)
    r = returns(s, 5)
    assert r[:4].to_list() == [None, None, None, None]
    assert r[5] is not None


def test_returns_negative():
    s = pl.Series([100.0, 95.0, 110.0])
    r = returns(s, 1)
    assert r[1] == pytest.approx((95 / 100) - 1)
    assert r[2] == pytest.approx((110 / 95) - 1)


# --- Distance to MA ---


def test_distance_to_ma():
    close = _sample_series(10)
    ma = sma(close, 3)
    d = distance_to_ma(close, ma)
    assert d[:1].is_null().all()  # warmup for sma(3)
    assert d[2] == pytest.approx((3 / ((1 + 2 + 3) / 3)) - 1)


def test_above_ma():
    close = pl.Series([10.0, 11.0, 9.0, 12.0])
    ma = pl.Series([10.0, 10.5, 10.0, 10.5])
    a = above_ma(close, ma)
    assert a[0] is False
    assert a[1] is True
    assert a[2] is False
    assert a[3] is True


# --- ATR% ---


def test_atr_pct_nonnegative():
    s = _sample_series(10)
    h = s + 0.5
    low_s = s - 0.5
    atr = (h - low_s).rolling_mean(window_size=3)
    p = atr_pct(atr, s)
    assert (p.drop_nulls() >= 0).all()
    assert p[:2].is_null().all()


# --- Realized volatility ---


def test_realized_vol_nonnegative():
    s = _sample_series(50)
    rv = realized_vol(s, 21)
    assert (rv.drop_nulls() >= 0).all()
    assert rv[:20].is_null().all()  # warmup


def test_realized_vol_zero_for_constant():
    s = pl.Series([100.0] * 30)
    rv = realized_vol(s, 21)
    assert (rv.drop_nulls() == 0.0).all()


# --- Relative volume ---


def test_rvol():
    vol = pl.Series([100, 100, 100, 100, 200], dtype=pl.Float64)
    rv = relative_volume(vol, 3)
    assert rv[3] == pytest.approx(100 / ((100 + 100 + 100) / 3))
    assert rv[:2].is_null().all()  # warmup


# --- Dollar volume ---


def test_dollar_volume():
    dv = dollar_volume(pl.Series([100.0, 101.0]), pl.Series([1000, 1500]))
    assert dv[0] == 100 * 1000
    assert dv[1] == 101 * 1500


def test_avg_dollar_volume():
    close = pl.Series([100.0, 101.0, 102.0])
    vol = pl.Series([1000, 1500, 1200])
    adv = avg_dollar_volume(close, vol, 2)
    assert adv[:1].is_null().all()  # warmup
    assert adv[2] == pytest.approx(((101 * 1500) + (102 * 1200)) / 2)


# --- 52-week / high-low ---


def test_pct_off_high_low():
    close = _sample_series(10)
    h = close + 1.0
    low_s = close - 1.0
    ph = pct_off_high(close, h, 5)
    plw = pct_off_low(close, low_s, 5)
    assert (ph.drop_nulls() <= 0).all()
    assert (plw.drop_nulls() >= 0).all()


def test_is_new_high():
    h = pl.Series([10.0, 11.0, 12.0, 11.5, 11.0])
    nh = is_new_high(h, 3)
    assert nh[:2].is_null().all()  # warmup
    assert nh[2] is True  # 12 is new max of [10, 11, 12]
    assert nh[3] is False  # 11.5 < 12
    assert nh[4] is False  # 11 < 12


def test_is_new_low():
    low_s = pl.Series([10.0, 9.0, 8.0, 8.5, 9.0])
    nl = is_new_low(low_s, 3)
    assert nl[:2].is_null().all()  # warmup
    assert nl[2] is True  # 8 is new min of [10, 9, 8]
    assert nl[3] is False  # 8.5 > 8
    assert nl[4] is False  # 9 > 8


# --- Gap % ---


def test_gap_pct():
    open_ = pl.Series([105.0, 110.0])
    close = pl.Series([100.0, 108.0])
    g = gap_pct(open_, close)
    assert g[0] is None
    assert g[1] == pytest.approx((110 / 100) - 1)


# --- RSI bounds ---


def test_rsi_bounds():
    s = _sample_series(30)
    r = rsi(s, 14)
    assert (r.drop_nulls() >= 0).all()
    assert (r.drop_nulls() <= 100).all()


# --- MACD structure ---


def test_macd_structure():
    s = _sample_series(50)
    m = macd(s)
    assert "macd" in m
    assert "macd_ema" in m
    assert "histogram" in m
    assert len(m["macd"]) == len(s)
