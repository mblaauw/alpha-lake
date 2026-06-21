from __future__ import annotations

from datetime import UTC, date, datetime

import duckdb

from alpha_lake.security_master import (
    _reset_cache_for_test,
    mint_security_id,
    register,
    register_ticker_cik,
    resolve,
    resolve_ticker_to_cik,
)


def test_mint_security_id_deterministic():
    h1 = mint_security_id(figi="BBG000B9XVX7")
    h2 = mint_security_id(figi="BBG000B9XVX7")
    assert h1 == h2
    assert h1.startswith("sec_")
    assert len(h1) == 28


def test_mint_security_id_different_inputs():
    h1 = mint_security_id(figi="BBG000B9XVX7")
    h2 = mint_security_id(cik="0000320193")
    assert h1 != h2


def test_mint_security_id_priority():
    h_figi = mint_security_id(figi="BBG000B9XVX7", cik="0000320193")
    h_cik = mint_security_id(cik="0000320193")
    assert h_figi == mint_security_id(figi="BBG000B9XVX7")
    assert h_figi != h_cik


def test_mint_security_id_empty():
    assert mint_security_id() == ""


def test_register_and_resolve():
    con = duckdb.connect()
    con.execute("SET timezone = 'UTC'")
    register(
        con,
        symbol="AAPL",
        security_id="sec_aapl",
        effective_start=date(2020, 1, 1),
        available_at=datetime(2020, 1, 1, tzinfo=UTC),
        cik="0000320193",
    )
    sid = resolve(con, "AAPL")
    assert sid == "sec_aapl"
    con.close()


def test_register_and_resolve_in_pit():
    con = duckdb.connect()
    con.execute("SET timezone = 'UTC'")
    register(
        con,
        symbol="AAPL",
        security_id="sec_old",
        effective_start=date(2015, 1, 1),
        effective_end=date(2019, 12, 31),
        available_at=datetime(2019, 1, 1, tzinfo=UTC),
    )
    register(
        con,
        symbol="AAPL",
        security_id="sec_new",
        effective_start=date(2020, 1, 1),
        available_at=datetime(2020, 1, 1, tzinfo=UTC),
    )
    old = resolve(con, "AAPL", as_of=date(2019, 6, 1))
    assert old == "sec_old"
    new = resolve(con, "AAPL", as_of=date(2020, 6, 1))
    assert new == "sec_new"
    con.close()


def test_resolve_ticker_cik_cache():
    _reset_cache_for_test()
    register_ticker_cik("AAPL", "0000320193")
    cik = resolve_ticker_to_cik("aapl")
    assert cik == "0000320193"


def test_resolve_ticker_case_insensitive():
    _reset_cache_for_test()
    register_ticker_cik("MSFT", "0000789019")
    assert resolve_ticker_to_cik("msft") == "0000789019"
    assert resolve_ticker_to_cik("MSFT") == "0000789019"


def test_resolve_ticker_not_found():
    _reset_cache_for_test()
    assert resolve_ticker_to_cik("UNKNOWN") is None
