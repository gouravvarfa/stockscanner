import pandas as pd

from backend.indicators.resample import to_monthly, to_weekly


def _daily_df(start, periods):
    idx = pd.bdate_range(start, periods=periods)
    return pd.DataFrame(
        {
            "open": range(periods),
            "high": range(periods),
            "low": range(periods),
            "close": range(periods),
            "volume": [100] * periods,
        },
        index=idx,
    )


def test_weekly_drops_in_progress_week():
    # Business days from a Monday through the following Wednesday: the final
    # week (Mon-Wed) is incomplete and must not appear as its own bar.
    df = _daily_df("2024-01-01", 8)  # Mon 1 Jan .. Wed 10 Jan
    weekly = to_weekly(df)
    # Complete weeks only: week ending Fri 5 Jan. Week ending Fri 12 Jan is in progress.
    assert weekly.index[-1] == pd.Timestamp("2024-01-05")


def test_weekly_keeps_fully_covered_week():
    df = _daily_df("2024-01-01", 5)  # Mon 1 Jan .. Fri 5 Jan, a complete week
    weekly = to_weekly(df)
    assert weekly.index[-1] == pd.Timestamp("2024-01-05")
    assert weekly["close"].iloc[-1] == 4  # last close of the week


def test_monthly_drops_in_progress_month():
    df = _daily_df("2024-01-29", 5)  # spills into February, February incomplete
    monthly = to_monthly(df)
    assert monthly.index[-1] < pd.Timestamp("2024-02-29")


# ---------------------------------------------------------------------------
# include_partial (2026-09-25, APLAPOLLO chart bug): the trailing in-progress
# bucket is dropped by DEFAULT (every existing test above, and every existing
# strategy caller, is completely unaffected) but can be explicitly kept for
# LIVE display (chart_service.py only).
# ---------------------------------------------------------------------------

def test_monthly_include_partial_keeps_the_in_progress_month():
    df = _daily_df("2024-01-29", 5)  # 2 Jan days + 3 Feb days, February incomplete
    monthly = to_monthly(df, include_partial=True)
    assert monthly.index[-1].month == 2
    assert monthly.index[-1].year == 2024


def test_monthly_include_partial_current_month_ohlc_built_from_available_days_only():
    # Business days Mon 29 Jan .. Fri 2 Feb: 3 January days (close 0, 1, 2),
    # 2 February days so far (close 3, 4) - the partial Feb candle must be
    # built from exactly those 2 February days, not the whole month.
    df = _daily_df("2024-01-29", 5)
    monthly = to_monthly(df, include_partial=True)
    feb = monthly.iloc[-1]
    assert feb["open"] == 3  # first Feb day's open
    assert feb["high"] == 4  # highest Feb high so far
    assert feb["low"] == 3  # lowest Feb low so far
    assert feb["close"] == 4  # latest available Feb close
    assert feb["volume"] == 200  # cumulative Feb volume so far (2 days x 100)


def test_monthly_include_partial_previous_completed_month_still_identifiable():
    df = _daily_df("2024-01-29", 5)
    monthly = to_monthly(df, include_partial=True)
    jan = monthly.iloc[-2]
    assert jan.name.month == 1
    assert jan["close"] == 2  # last of the 3 January days, unaffected by the partial Feb bucket


def test_weekly_include_partial_keeps_the_in_progress_week():
    df = _daily_df("2024-01-01", 8)  # Mon 1 Jan .. Wed 10 Jan, second week incomplete
    weekly = to_weekly(df, include_partial=True)
    assert weekly.index[-1] == pd.Timestamp("2024-01-12")  # the in-progress week's Friday label
    assert weekly["close"].iloc[-1] == 7  # last available day (Wed) of that in-progress week


def test_include_partial_default_is_false_existing_callers_unaffected():
    """Every existing to_monthly()/to_weekly() call in the codebase (every
    strategy confirmation path) omits include_partial entirely — this proves
    the default is still the old, safe "drop the in-progress period"
    behavior, so adding the parameter cannot silently change any of them."""
    df = _daily_df("2024-01-29", 5)
    assert to_monthly(df).index[-1] == to_monthly(df, include_partial=False).index[-1]
    assert to_monthly(df).index[-1] < pd.Timestamp("2024-02-29")
