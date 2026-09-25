import datetime as dt

from backend.live.market_hours import IST, is_trading_day, market_state


def test_before_market_open_is_pre_market():
    now = dt.datetime(2026, 9, 25, 9, 0, tzinfo=IST)  # Friday, 9:00 AM
    assert market_state(now) == "PRE_MARKET"


def test_during_session_is_market_open():
    now = dt.datetime(2026, 9, 25, 11, 30, tzinfo=IST)
    assert market_state(now) == "MARKET_OPEN"


def test_exactly_at_open_boundary_is_market_open():
    now = dt.datetime(2026, 9, 25, 9, 15, tzinfo=IST)
    assert market_state(now) == "MARKET_OPEN"


def test_exactly_at_close_boundary_is_market_closed():
    now = dt.datetime(2026, 9, 25, 15, 30, tzinfo=IST)
    assert market_state(now) == "MARKET_CLOSED"


def test_after_close_is_market_closed():
    now = dt.datetime(2026, 9, 25, 16, 0, tzinfo=IST)
    assert market_state(now) == "MARKET_CLOSED"


def test_saturday_is_market_closed_regardless_of_time():
    now = dt.datetime(2026, 9, 26, 11, 0, tzinfo=IST)  # Saturday
    assert market_state(now) == "MARKET_CLOSED"


def test_sunday_is_market_closed_regardless_of_time():
    now = dt.datetime(2026, 9, 27, 11, 0, tzinfo=IST)  # Sunday
    assert market_state(now) == "MARKET_CLOSED"


def test_naive_datetime_is_treated_as_ist():
    now = dt.datetime(2026, 9, 25, 11, 30)  # no tzinfo
    assert market_state(now) == "MARKET_OPEN"


def test_other_timezone_is_converted_to_ist_before_deciding():
    utc = dt.timezone.utc
    # 07:00 UTC == 12:30 IST (UTC+5:30) - well inside the session.
    now = dt.datetime(2026, 9, 25, 7, 0, tzinfo=utc)
    assert market_state(now) == "MARKET_OPEN"


def test_is_trading_day_excludes_weekends():
    assert is_trading_day(dt.date(2026, 9, 25)) is True  # Friday
    assert is_trading_day(dt.date(2026, 9, 26)) is False  # Saturday
    assert is_trading_day(dt.date(2026, 9, 27)) is False  # Sunday


def test_is_trading_day_excludes_injected_holidays():
    holidays = frozenset({dt.date(2026, 9, 25)})
    assert is_trading_day(dt.date(2026, 9, 25), holidays) is False
    assert is_trading_day(dt.date(2026, 9, 24), holidays) is True
