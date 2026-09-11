from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from backend.config.strategy_config import FibonacciConfig


@dataclass(frozen=True)
class FibonacciLevel:
    ratio: float
    price: float
    distance_pct: float  # (current_price - level_price) / level_price * 100


@dataclass(frozen=True)
class FibonacciAnalysis:
    swing_high: float
    swing_low: float
    swing_high_date: pd.Timestamp
    swing_low_date: pd.Timestamp
    direction: str  # "uptrend_retracement" (low->high, retracing down) or "downtrend_retracement"
    current_price: float
    levels: list[FibonacciLevel]
    nearest_level: FibonacciLevel
    in_preferred_zone: bool


def _select_swing(high: pd.Series, low: pd.Series, lookback_bars: int) -> tuple[pd.Timestamp, float, pd.Timestamp, float]:
    """Most relevant recent swing = the highest high and lowest low within the lookback window,
    ordered chronologically so the retracement direction can be inferred."""
    window_high = high.iloc[-lookback_bars:]
    window_low = low.iloc[-lookback_bars:]

    high_date = window_high.idxmax()
    high_price = float(window_high.max())
    low_date = window_low.idxmin()
    low_price = float(window_low.min())

    return high_date, high_price, low_date, low_price


def calculate_fibonacci(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    config: FibonacciConfig,
) -> FibonacciAnalysis | None:
    if len(close) < 2:
        return None

    lookback = min(config.swing_lookback_bars, len(close))
    high_date, high_price, low_date, low_price = _select_swing(high, low, lookback)

    if high_price <= low_price:
        return None

    current_price = float(close.iloc[-1])
    swing_range = high_price - low_price

    # If the high came after the low, price rallied then may retrace down (uptrend retracement).
    # If the low came after the high, price fell then may retrace up (downtrend retracement).
    direction = "uptrend_retracement" if high_date >= low_date else "downtrend_retracement"

    levels: list[FibonacciLevel] = []
    for ratio in config.levels:
        if direction == "uptrend_retracement":
            level_price = high_price - swing_range * ratio
        else:
            level_price = low_price + swing_range * ratio
        distance_pct = (current_price - level_price) / level_price * 100.0
        levels.append(FibonacciLevel(ratio=ratio, price=level_price, distance_pct=distance_pct))

    nearest = min(levels, key=lambda lvl: abs(lvl.distance_pct))
    in_preferred_zone = (
        nearest.ratio in config.preferred_zones
        and abs(nearest.distance_pct) <= config.zone_tolerance_pct
    )

    return FibonacciAnalysis(
        swing_high=high_price,
        swing_low=low_price,
        swing_high_date=high_date,
        swing_low_date=low_date,
        direction=direction,
        current_price=current_price,
        levels=levels,
        nearest_level=nearest,
        in_preferred_zone=in_preferred_zone,
    )


def has_bullish_confirmation(close: pd.Series, analysis: FibonacciAnalysis, confirmation_bars: int = 2) -> bool:
    """
    A weak, explicit confirmation check: price has closed higher over the last
    `confirmation_bars` bars while sitting in the preferred fib zone. This does
    NOT assume every retracement is bullish — callers must check both
    in_preferred_zone AND this confirmation before treating the zone as supportive.
    """
    if not analysis.in_preferred_zone or len(close) < confirmation_bars + 1:
        return False
    recent = close.iloc[-(confirmation_bars + 1):]
    return bool(recent.iloc[-1] > recent.iloc[0])
