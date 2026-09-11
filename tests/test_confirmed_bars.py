import datetime as dt

import pandas as pd

from backend.indicators.confirmed_bars import drop_incomplete_trailing_bars, drop_incomplete_trailing_daily_bar


def test_drops_still_forming_15m_bar():
    # Bars at 09:15, 09:30, 09:45 (start times). "Now" is 09:52 -> the 09:45
    # bar (closes at 10:00) has not fully elapsed yet and must be dropped.
    idx = pd.to_datetime(["2024-06-03 09:15", "2024-06-03 09:30", "2024-06-03 09:45"])
    df = pd.DataFrame({"close": [100, 101, 102]}, index=idx)
    now = dt.datetime(2024, 6, 3, 9, 52)

    result = drop_incomplete_trailing_bars(df, interval_minutes=15, now=now)
    assert len(result) == 2
    assert result.index[-1] == idx[1]


def test_keeps_bar_exactly_at_close_boundary():
    idx = pd.to_datetime(["2024-06-03 09:15", "2024-06-03 09:30"])
    df = pd.DataFrame({"close": [100, 101]}, index=idx)
    now = dt.datetime(2024, 6, 3, 9, 45)  # exactly when the 09:30 bar closes

    result = drop_incomplete_trailing_bars(df, interval_minutes=15, now=now)
    assert len(result) == 2


def test_drops_still_forming_1h_bar():
    idx = pd.to_datetime(["2024-06-03 09:15", "2024-06-03 10:15"])
    df = pd.DataFrame({"close": [100, 101]}, index=idx)
    now = dt.datetime(2024, 6, 3, 10, 50)  # 10:15 bar closes at 11:15, not yet

    result = drop_incomplete_trailing_bars(df, interval_minutes=60, now=now)
    assert len(result) == 1
    assert result.index[0] == idx[0]


def test_empty_input_returns_empty():
    df = pd.DataFrame({"close": []})
    result = drop_incomplete_trailing_bars(df, interval_minutes=15, now=dt.datetime.now())
    assert result.empty


def test_drops_todays_daily_bar_before_market_close():
    idx = pd.to_datetime(["2024-06-03", "2024-06-04"])
    df = pd.DataFrame({"close": [100, 101]}, index=idx)
    now = dt.datetime(2024, 6, 4, 13, 0)  # mid-session on the 4th

    result = drop_incomplete_trailing_daily_bar(df, now)
    assert len(result) == 1
    assert result.index[-1] == idx[0]


def test_keeps_todays_daily_bar_after_market_close():
    idx = pd.to_datetime(["2024-06-03", "2024-06-04"])
    df = pd.DataFrame({"close": [100, 101]}, index=idx)
    now = dt.datetime(2024, 6, 4, 16, 0)  # after 15:30 close

    result = drop_incomplete_trailing_daily_bar(df, now)
    assert len(result) == 2


def test_keeps_all_bars_when_latest_is_a_past_day():
    idx = pd.to_datetime(["2024-06-03", "2024-06-04"])
    df = pd.DataFrame({"close": [100, 101]}, index=idx)
    now = dt.datetime(2024, 6, 5, 9, 0)  # next day, before that day's own bar exists

    result = drop_incomplete_trailing_daily_bar(df, now)
    assert len(result) == 2
