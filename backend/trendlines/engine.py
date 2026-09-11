"""
Key Reversal and Trendline Breakout detection for the Value Buy strategy.

Both are defined from real, historical price structure — never a bare
"today's price > previous high" check (explicitly forbidden by the spec).
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from backend.divergence.swing import SwingPoint, find_swing_points


@dataclass
class KeyReversalResult:
    detected: bool
    date: pd.Timestamp | None = None
    reason: str | None = None


@dataclass
class TrendlineBreakoutResult:
    detected: bool
    anchor1: SwingPoint | None = None
    anchor2: SwingPoint | None = None
    breakout_date: pd.Timestamp | None = None
    breakout_price: float | None = None
    trendline_price_at_breakout: float | None = None
    reason: str | None = None


def detect_key_reversal(daily_ohlcv: pd.DataFrame) -> KeyReversalResult:
    """
    Bullish key reversal (the relevant direction for Value Buy): the latest
    confirmed daily bar makes a new low versus the prior bar, then closes
    above the prior bar's close AND above its own open — i.e. sellers pushed
    price to a fresh low intraday and buyers reversed it by the close.
    """
    if len(daily_ohlcv) < 2:
        return KeyReversalResult(detected=False, reason="Insufficient daily history.")

    prev = daily_ohlcv.iloc[-2]
    today = daily_ohlcv.iloc[-1]

    made_new_low = today["low"] < prev["low"]
    reversed_up = today["close"] > prev["close"] and today["close"] > today["open"]

    if made_new_low and reversed_up:
        return KeyReversalResult(detected=True, date=daily_ohlcv.index[-1])
    return KeyReversalResult(
        detected=False,
        reason="Latest confirmed daily bar does not show a new-low-then-reversal pattern.",
    )


def detect_trendline_breakout(
    daily_ohlcv: pd.DataFrame, swing_lookback: int = 5, min_swing_points: int = 2
) -> TrendlineBreakoutResult:
    """
    Fits a descending resistance line through the two most recent distinct
    swing highs (real fractal pivots, see backend/divergence/swing.py), then
    checks whether the latest confirmed close breaks above that line
    projected to today. Only meaningful when the line actually descends
    (a rising line isn't overhead resistance to break through).
    """
    if len(daily_ohlcv) < swing_lookback * 2 + 5:
        return TrendlineBreakoutResult(detected=False, reason="Insufficient daily history for swing detection.")

    high, low = daily_ohlcv["high"], daily_ohlcv["low"]
    swings = find_swing_points(high, low, swing_lookback)
    highs = [p for p in swings if p.kind == "high"]

    if len(highs) < min_swing_points:
        return TrendlineBreakoutResult(detected=False, reason="Not enough confirmed swing highs to fit a trendline.")

    anchor1, anchor2 = highs[-2], highs[-1]
    if anchor2.index == anchor1.index or anchor2.price >= anchor1.price:
        return TrendlineBreakoutResult(
            detected=False, reason="Most recent swing highs do not form a descending trendline."
        )

    # Linear projection from anchor1 -> anchor2, extended to the latest bar.
    slope = (anchor2.price - anchor1.price) / (anchor2.index - anchor1.index)
    latest_index = len(daily_ohlcv) - 1
    trendline_price_today = anchor2.price + slope * (latest_index - anchor2.index)

    latest_close = float(daily_ohlcv["close"].iloc[-1])
    if latest_close > trendline_price_today:
        return TrendlineBreakoutResult(
            detected=True,
            anchor1=anchor1,
            anchor2=anchor2,
            breakout_date=daily_ohlcv.index[-1],
            breakout_price=latest_close,
            trendline_price_at_breakout=float(trendline_price_today),
        )
    return TrendlineBreakoutResult(
        detected=False,
        anchor1=anchor1,
        anchor2=anchor2,
        trendline_price_at_breakout=float(trendline_price_today),
        reason="Latest close has not broken above the descending trendline.",
    )
