from __future__ import annotations

import datetime
from functools import lru_cache

import exchange_calendars as ec

_EXCHANGE_MAP: dict[str, str] = {
    "XNYS": "XNYS",
    "NYSE": "XNYS",
    "XNAS": "XNAS",
    "NASDAQ": "XNAS",
    "XASE": "XASE",
    "AMEX": "XASE",
}


def _resolve(code: str) -> str:
    return _EXCHANGE_MAP.get(code.upper(), code.upper())


@lru_cache(maxsize=32)
def _get_calendar(code: str) -> ec.ExchangeCalendar:
    return ec.get_calendar(code)


def is_trading_day(dt: datetime.date, exchange: str = "XNYS") -> bool:
    cal = _get_calendar(_resolve(exchange))
    return cal.is_session(dt.isoformat())


def previous_trading_day(dt: datetime.date, exchange: str = "XNYS") -> datetime.date:
    cal = _get_calendar(_resolve(exchange))
    return cal.date_to_session(dt.isoformat(), direction="previous").date()


def next_trading_day(dt: datetime.date, exchange: str = "XNYS") -> datetime.date:
    cal = _get_calendar(_resolve(exchange))
    return cal.date_to_session(dt.isoformat(), direction="next").date()


def shift_trading_days(dt: datetime.date, n: int, exchange: str = "XNYS") -> datetime.date:
    cal = _get_calendar(_resolve(exchange))
    if n == 0:
        return dt
    fn = cal.next_session if n > 0 else cal.previous_session
    current = dt.isoformat()
    for _ in range(abs(n)):
        current = fn(current)
    if isinstance(current, str):
        return datetime.date.fromisoformat(current)
    return current.date()


def trading_days_in_range(
    start: datetime.date,
    end: datetime.date,
    exchange: str = "XNYS",
) -> list[datetime.date]:
    cal = _get_calendar(_resolve(exchange))
    return [s.date() for s in cal.sessions_in_range(start.isoformat(), end.isoformat())]
