from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from backend.config.expiry_level_5_config import ExpiryLevel5Config
from backend.fibonacci.engine import FibonacciAnalysis, calculate_fibonacci


@dataclass
class ExpiryLevel5Signal:
    symbol: str
    signal_date: pd.Timestamp
    swing_high: float
    swing_low: float
    fib_38_2: float | None
    fib_50: float | None
    fib_61_8: float
    support_price: float
    support_confirmed: bool
    confirmation_candle: dict[str, float]
    previous_candle_high: float
    confirmation_close_above_previous_high: bool
    reason: str
    strategy: str = "EXPIRY_LEVEL_5"
    signal: str = "BUY_CE"
    instrument_type: str = "STOCK_FUTURE"


def _level_price(analysis: FibonacciAnalysis, ratio: float) -> float | None:
    for level in analysis.levels:
        if abs(level.ratio - ratio) < 1e-9:
            return level.price
    return None


def detect_expiry_level_5_signal(
    symbol: str, ohlc: pd.DataFrame, config: ExpiryLevel5Config
) -> ExpiryLevel5Signal | None:
    """
    `ohlc` must contain ONLY confirmed/closed candles (caller drops any
    still-forming bar) and must be chronologically ascending.

    Setup, evaluated with the LATEST bar as the candidate confirmation candle:
    1. A genuine historical touch of the 38.2%-61.8% Fibonacci retracement
       ZONE (the "golden pocket"), not just the single 61.8% point: some
       earlier bar's LOW fell within that zone, +/- `fib_61_8_tolerance_percent`
       padding on both edges (searching backward from the latest bar for the
       NEAREST such touch — this is what lets a fresh touch after an earlier
       setup produce a new, independent signal rather than being masked by
       the old one).
    2. Support held: no bar from that touch through the latest bar closed
       decisively below the zone's deep (61.8%) edge (more than the
       tolerance band under it).
    3. The FIRST bar after the touch where close > fib_61_8 AND
       close > previous bar's high is the confirmation candle. A signal only
       fires if that first-qualifying bar IS the latest bar — this is what
       makes the signal fire exactly once per setup (subsequent scans see an
       unrelated, later "latest bar" and naturally stop matching) rather than
       repeating on every candle the setup remains true.
    """
    if len(ohlc) < 3:
        return None

    high, low, close = ohlc["high"], ohlc["low"], ohlc["close"]
    analysis = calculate_fibonacci(high, low, close, config.fibonacci)
    if analysis is None:
        return None

    fib_618 = _level_price(analysis, 0.618)
    if fib_618 is None or fib_618 <= 0:
        return None
    fib_50 = _level_price(analysis, 0.5)
    fib_382 = _level_price(analysis, 0.382)

    # The retracement ZONE spans 38.2% to 61.8% — whichever of the two is the
    # deeper (lower-price) edge depends on retracement direction (see
    # calculate_fibonacci), so take min/max rather than assuming order. If
    # 0.382 isn't configured as a level, the zone collapses to the single
    # 61.8% point (unchanged prior behavior).
    zone_deep_edge = min(fib_382, fib_618) if fib_382 is not None else fib_618
    zone_shallow_edge = max(fib_382, fib_618) if fib_382 is not None else fib_618

    tolerance = fib_618 * config.fib_61_8_tolerance_percent / 100.0
    lower_bound = zone_deep_edge - tolerance
    upper_bound = zone_shallow_edge + tolerance
    decisive_break_level = zone_deep_edge - tolerance

    latest_index = len(ohlc) - 1

    touch_index: int | None = None
    for i in range(latest_index - 1, -1, -1):
        if lower_bound <= low.iloc[i] <= upper_bound:
            touch_index = i
            break
    if touch_index is None:
        return None  # price never actually retraced into the 38.2%-61.8% zone

    for i in range(touch_index, latest_index + 1):
        if close.iloc[i] < decisive_break_level:
            return None  # support did not hold

    first_confirm_index: int | None = None
    for i in range(touch_index + 1, latest_index + 1):
        previous_high = high.iloc[i - 1]
        if close.iloc[i] > fib_618 and close.iloc[i] > previous_high:
            first_confirm_index = i
            break

    if first_confirm_index is None or first_confirm_index != latest_index:
        return None  # no confirmation yet, or it already happened on an earlier bar

    confirm_close = float(close.iloc[latest_index])
    previous_high_val = float(high.iloc[latest_index - 1])
    touch_low = float(low.iloc[touch_index])

    candle: dict[str, float] = {
        "open": float(ohlc["open"].iloc[latest_index]),
        "high": float(high.iloc[latest_index]),
        "low": float(low.iloc[latest_index]),
        "close": confirm_close,
    }

    return ExpiryLevel5Signal(
        symbol=symbol,
        signal_date=ohlc.index[latest_index],
        swing_high=analysis.swing_high,
        swing_low=analysis.swing_low,
        fib_38_2=fib_382,
        fib_50=fib_50,
        fib_61_8=fib_618,
        support_price=touch_low,
        support_confirmed=True,
        confirmation_candle=candle,
        previous_candle_high=previous_high_val,
        confirmation_close_above_previous_high=True,
        reason=(
            f"38.2%-61.8% Fibonacci zone support ({zone_deep_edge:.2f}-{zone_shallow_edge:.2f}) touched on "
            f"{ohlc.index[touch_index].date()} (low {touch_low:.2f}), followed by a bullish candle closing at "
            f"{confirm_close:.2f} above the 61.8% level ({fib_618:.2f}) and above the previous candle's high "
            f"of {previous_high_val:.2f}."
        ),
    )
