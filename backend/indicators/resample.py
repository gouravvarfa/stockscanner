from __future__ import annotations

import pandas as pd

OHLCV_AGG = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "volume": "sum",
}


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """
    Resample a daily OHLCV DataFrame (DatetimeIndex, columns open/high/low/close/volume)
    to a coarser timeframe. rule: "W-FRI" for NSE-aligned weekly (Fri close),
    "ME" for monthly.

    The trailing bar is dropped whenever it represents a still-in-progress
    period (its resample label — the period's calendar end — falls after the
    last actual daily bar we have). Without this, an in-progress week/month
    collapses to a single day's data and its RSI/return silently degenerates
    to the daily value, which is wrong, not just imprecise. Tapetide's own
    get_index_performance applies the same rule ("only COMPLETED periods are
    counted").
    """
    cols = [c for c in OHLCV_AGG if c in df.columns]
    resampled = (
        df[cols]
        .resample(rule, label="right", closed="right")
        .agg({c: OHLCV_AGG[c] for c in cols})
        .dropna(how="all")
    )
    if len(resampled) and len(df) and resampled.index[-1] > df.index.max():
        resampled = resampled.iloc[:-1]
    return resampled


def to_weekly(df: pd.DataFrame) -> pd.DataFrame:
    return resample_ohlcv(df, "W-FRI")


def to_monthly(df: pd.DataFrame) -> pd.DataFrame:
    return resample_ohlcv(df, "ME")
