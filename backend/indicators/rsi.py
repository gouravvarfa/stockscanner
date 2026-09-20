from __future__ import annotations

import numpy as np
import pandas as pd


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """
    Wilder's RSI with the classic seeding convention: the first average
    gain/loss is a simple mean of the first `period` deltas, and every
    subsequent value applies Wilder's recursive smoothing
    (avg = (prev_avg * (period - 1) + current) / period).
    """
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = pd.Series(index=close.index, dtype=float)
    avg_loss = pd.Series(index=close.index, dtype=float)

    if len(close) <= period:
        return pd.Series([float("nan")] * len(close), index=close.index)

    first_valid = period  # delta.iloc[1..period] are the first `period` deltas
    avg_gain.iloc[first_valid] = gain.iloc[1 : first_valid + 1].mean()
    avg_loss.iloc[first_valid] = loss.iloc[1 : first_valid + 1].mean()

    # Same recursion, same operation order, on plain float64 arrays (the
    # per-element pandas .iloc reads/writes were the hot spot).
    g = gain.to_numpy(dtype=float)
    l = loss.to_numpy(dtype=float)
    ag = np.full(len(close), np.nan)
    al = np.full(len(close), np.nan)
    ag[first_valid] = avg_gain.iloc[first_valid]
    al[first_valid] = avg_loss.iloc[first_valid]
    pm1 = period - 1
    for i in range(first_valid + 1, len(close)):
        ag[i] = (ag[i - 1] * pm1 + g[i]) / period
        al[i] = (al[i - 1] * pm1 + l[i]) / period
    avg_gain = pd.Series(ag, index=close.index)
    avg_loss = pd.Series(al, index=close.index)

    rs = avg_gain / avg_loss.replace(0.0, pd.NA)
    result = 100.0 - (100.0 / (1.0 + rs))
    result = result.where(avg_loss != 0.0, 100.0)
    return result
