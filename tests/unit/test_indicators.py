import polars as pl
import pytest

from alpha_lake.derived.indicators import (
    atr, bollinger_bands, ema, macd, obv, rsi, sma, vwap,
)


def test_sma():
    s = pl.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    result = sma(s, 3)
    assert result[2] == 2.0
    assert result[4] == 4.0


def test_ema():
    s = pl.Series([1.0, 2.0, 3.0])
    result = ema(s, 3)
    assert result[0] == 1.0
    assert result[2] > 2.0


def test_rsi():
    s = pl.Series([45.0, 46.0, 47.0, 48.0, 49.0, 50.0])
    r = rsi(s)
    assert r[0] is not None


def test_bollinger_bands():
    s = pl.Series([10.0] * 25)
    bands = bollinger_bands(s)
    assert "upper" in bands
    assert "lower" in bands
    for v in bands["upper"].drop_nulls():
        assert v == pytest.approx(10.0, abs=0.01)


def test_atr():
    h = pl.Series([11.0, 12.0, 13.0])
    l = pl.Series([9.0, 8.0, 7.0])
    c = pl.Series([10.0, 11.0, 12.0])
    t = atr(h, l, c)
    assert len(t) == 3


def test_obv():
    c = pl.Series([100.0, 102.0, 101.0])
    v = pl.Series([1000, 2000, 1500])
    o = obv(c, v)
    assert o[0] == 1000
    assert o[1] == 3000


def test_vwap():
    h = pl.Series([11.0, 12.0])
    l = pl.Series([9.0, 8.0])
    c = pl.Series([10.0, 11.0])
    v = pl.Series([1000, 2000])
    w = vwap(h, l, c, v)
    assert w[1] > w[0]


def test_macd():
    s = pl.Series([10.0, 11.0, 12.0, 13.0, 14.0, 15.0])
    m = macd(s)
    assert "macd" in m
    assert "signal" in m
    assert "histogram" in m
