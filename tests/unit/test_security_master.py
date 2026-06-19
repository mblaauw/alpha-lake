from datetime import UTC, date, datetime

import duckdb

from alpha_lake.security_master import mint_security_id, register, resolve


def test_mint_security_id_deterministic():
    h1 = mint_security_id(figi="BBG000B9XVX7")
    h2 = mint_security_id(figi="BBG000B9XVX7")
    assert h1 == h2
    assert h1.startswith("sec_")
    assert len(h1) == 28  # "sec_" + 24 hex chars


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
    sid = mint_security_id(figi="BBG000B9XVX7")
    register(con, "AAPL", sid, date(2020, 1, 1),
             available_at=datetime(2020, 1, 1, tzinfo=UTC),
             name="Apple Inc.", exchange="XNAS")
    result = resolve(con, "AAPL")
    assert result == sid


def test_resolve_pit():
    con = duckdb.connect()
    sid = mint_security_id(figi="BBG000B9XVX7")
    register(con, "AAPL", sid, date(2020, 1, 1),
             available_at=datetime(2020, 1, 1, tzinfo=UTC))
    # Before effective_start → no match
    before = resolve(con, "AAPL", as_of=date(2019, 12, 31))
    assert before is None
    # After effective_start → match
    after = resolve(con, "AAPL", as_of=date(2020, 6, 15))
    assert after == sid


def test_symbol_reuse():
    con = duckdb.connect()
    old_sid = mint_security_id(figi="OLD123")
    new_sid = mint_security_id(figi="NEW456")
    register(con, "TICKER", old_sid, date(2020, 1, 1), effective_end=date(2022, 12, 31),
             available_at=datetime(2020, 1, 1, tzinfo=UTC))
    register(con, "TICKER", new_sid, date(2023, 1, 1),
             available_at=datetime(2023, 1, 1, tzinfo=UTC))

    assert resolve(con, "TICKER", as_of=date(2021, 6, 1)) == old_sid
    assert resolve(con, "TICKER", as_of=date(2023, 6, 1)) == new_sid
    assert resolve(con, "TICKER", as_of=date(2019, 1, 1)) is None
