from __future__ import annotations

import abc
import datetime


class Clock(abc.ABC):
    """Interface for time sources — replaceable in tests/replay."""

    @abc.abstractmethod
    def now(self) -> datetime.datetime:
        """Current UTC instant."""
        ...

    @abc.abstractmethod
    def today(self) -> datetime.date:
        """Current UTC date."""
        ...


class SystemClock(Clock):
    """Production clock using real UTC system time."""

    def now(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.timezone.utc)

    def today(self) -> datetime.date:
        return datetime.datetime.now(datetime.timezone.utc).date()


class FixedClock(Clock):
    """Test clock returning a fixed datetime."""

    def __init__(self, fixed: datetime.datetime | None = None):
        self._fixed = fixed or datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)

    def now(self) -> datetime.datetime:
        return self._fixed

    def today(self) -> datetime.date:
        return self._fixed.date()


# Module-level default — tests can override via set_clock()
_clock: Clock = SystemClock()


def get_clock() -> Clock:
    return _clock


def set_clock(clock: Clock) -> None:
    global _clock
    _clock = clock
