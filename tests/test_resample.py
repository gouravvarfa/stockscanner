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
