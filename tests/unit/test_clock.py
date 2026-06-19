from datetime import datetime, timezone

from alpha_lake.clock import FixedClock, SystemClock, get_clock, set_clock


def test_system_clock_returns_utc():
    clock = SystemClock()
    now = clock.now()
    assert now.tzinfo is not None
    assert now.tzinfo.utcoffset(now).total_seconds() == 0


def test_fixed_clock_returns_fixed_time():
    fixed = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    clock = FixedClock(fixed)
    assert clock.now() == fixed
    assert clock.today() == fixed.date()


def test_fixed_clock_default():
    clock = FixedClock()
    assert clock.now().year == 2026


def test_set_and_get_clock():
    original = get_clock()
    fixed = FixedClock()
    set_clock(fixed)
    try:
        assert get_clock() is fixed
    finally:
        set_clock(original)
