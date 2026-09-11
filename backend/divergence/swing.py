from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class SwingPoint:
    index: int
    date: pd.Timestamp
    price: float
    kind: str  # "high" or "low"


def find_swing_points(
    high: pd.Series, low: pd.Series, lookback: int
) -> list[SwingPoint]:
    """
    A bar is a swing high if its high is the strictest max within `lookback`
    bars on both sides; a swing low is the analogous strict min on lows.
    This is real fractal/pivot swing detection, not a plain peak-to-peak
    comparison of the raw series.
    """
    points: list[SwingPoint] = []
    n = len(high)
    for i in range(lookback, n - lookback):
        window_high = high.iloc[i - lookback : i + lookback + 1]
        if high.iloc[i] == window_high.max() and (window_high == high.iloc[i]).sum() == 1:
            points.append(SwingPoint(index=i, date=high.index[i], price=float(high.iloc[i]), kind="high"))

        window_low = low.iloc[i - lookback : i + lookback + 1]
        if low.iloc[i] == window_low.min() and (window_low == low.iloc[i]).sum() == 1:
            points.append(SwingPoint(index=i, date=low.index[i], price=float(low.iloc[i]), kind="low"))

    points.sort(key=lambda p: p.index)
    return points
