from __future__ import annotations

import pandas as pd


def average_volume(volume: pd.Series, period: int = 20) -> pd.Series:
    return volume.rolling(window=period, min_periods=period).mean()


def volume_ratio(volume: pd.Series, period: int = 20) -> pd.Series:
    """Latest volume vs its own trailing average — >1 means above-average activity."""
    avg = average_volume(volume, period)
    return volume / avg


def distance_from_52w_high(close: pd.Series, high: pd.Series) -> pd.Series:
    rolling_high = high.rolling(window=252, min_periods=1).max()
    return (close - rolling_high) / rolling_high * 100.0


def distance_from_52w_low(close: pd.Series, low: pd.Series) -> pd.Series:
    rolling_low = low.rolling(window=252, min_periods=1).min()
    return (close - rolling_low) / rolling_low * 100.0
