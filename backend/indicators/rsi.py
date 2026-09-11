from __future__ import annotations

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

    for i in range(first_valid + 1, len(close)):
        avg_gain.iloc[i] = (avg_gain.iloc[i - 1] * (period - 1) + gain.iloc[i]) / period
        avg_loss.iloc[i] = (avg_loss.iloc[i - 1] * (period - 1) + loss.iloc[i]) / period

    rs = avg_gain / avg_loss.replace(0.0, pd.NA)
    result = 100.0 - (100.0 / (1.0 + rs))
    result = result.where(avg_loss != 0.0, 100.0)
    return result
