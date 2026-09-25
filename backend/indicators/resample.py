from __future__ import annotations

import pandas as pd

OHLCV_AGG = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "volume": "sum",
}


def resample_ohlcv(df: pd.DataFrame, rule: str, include_partial: bool = False) -> pd.DataFrame:
    """
    Resample a daily OHLCV DataFrame (DatetimeIndex, columns open/high/low/close/volume)
    to a coarser timeframe. rule: "W-FRI" for NSE-aligned weekly (Fri close),
    "ME" for monthly.

    By default (include_partial=False) the trailing bar is dropped whenever
    it represents a still-in-progress period (its resample label — the
    period's calendar end — falls after the last actual daily bar we have).
    Without this, an in-progress week/month collapses to a single day's
    data and its RSI/return silently degenerates to the daily value, which
    is wrong, not just imprecise. Tapetide's own get_index_performance
    applies the same rule ("only COMPLETED periods are counted"). Every
    STRATEGY confirmation path (PRD/NRD/GFS/Advanced GFS/System One/Value
    Buy/Cup Breakout's BREAKOUT_CONFIRMED) relies on this default — an
    incomplete candle must never be able to confirm a signal.

    include_partial=True (2026-09-25, APLAPOLLO chart bug) keeps that
    trailing in-progress bar instead of dropping it — built from whatever
    real, completed DAILY bars already exist for the current period (never
    fabricated). This is for LIVE display only (the chart itself, and any
    RSI/Bollinger Bands computed FROM the chart's own candle series) — see
    backend/services/chart_service.py, the only caller that passes it.
    """
    cols = [c for c in OHLCV_AGG if c in df.columns]
    resampled = (
        df[cols]
        .resample(rule, label="right", closed="right")
        .agg({c: OHLCV_AGG[c] for c in cols})
        .dropna(how="all")
    )
    if not include_partial and len(resampled) and len(df) and resampled.index[-1] > df.index.max():
        resampled = resampled.iloc[:-1]
    return resampled


def to_weekly(df: pd.DataFrame, include_partial: bool = False) -> pd.DataFrame:
    return resample_ohlcv(df, "W-FRI", include_partial=include_partial)


def to_monthly(df: pd.DataFrame, include_partial: bool = False) -> pd.DataFrame:
    return resample_ohlcv(df, "ME", include_partial=include_partial)
