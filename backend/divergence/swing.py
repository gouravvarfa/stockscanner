from __future__ import annotations

from dataclasses import dataclass

import numpy as np
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
    # Vectorized (numpy sliding windows) but semantically identical to the
    # original per-bar pandas loop: a bar is a pivot iff its value equals the
    # window extreme AND no other bar in the window shares that value.
    points: list[SwingPoint] = []
    n = len(high)
    if n < 2 * lookback + 1:
        return points
    size = 2 * lookback + 1
    h = high.to_numpy(dtype=float)
    lo = low.to_numpy(dtype=float)
    wh = np.lib.stride_tricks.sliding_window_view(h, size)
    wl = np.lib.stride_tricks.sliding_window_view(lo, size)
    ch, cl = wh[:, lookback], wl[:, lookback]
    with np.errstate(all="ignore"):
        is_high = (ch == np.nanmax(wh, axis=1)) & ((wh == ch[:, None]).sum(axis=1) == 1)
        is_low = (cl == np.nanmin(wl, axis=1)) & ((wl == cl[:, None]).sum(axis=1) == 1)
    index = high.index
    for k in np.nonzero(is_high | is_low)[0]:
        i = int(k) + lookback
        if is_high[k]:
            points.append(SwingPoint(index=i, date=index[i], price=float(h[i]), kind="high"))
        if is_low[k]:
            points.append(SwingPoint(index=i, date=index[i], price=float(lo[i]), kind="low"))

    points.sort(key=lambda p: p.index)
    return points
