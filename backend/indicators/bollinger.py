from __future__ import annotations

import pandas as pd


def bollinger_bands(close: pd.Series, period: int = 20, multiplier: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Classic Bollinger Bands: an SMA middle band plus/minus `multiplier`
    population-standard-deviations (ddof=0, matching the standard textbook
    definition). NaN for the warm-up period before a full `period`-length
    window is available.
    """
    middle = close.rolling(period).mean()
    std = close.rolling(period).std(ddof=0)
    upper = middle + multiplier * std
    lower = middle - multiplier * std
    return upper, middle, lower
