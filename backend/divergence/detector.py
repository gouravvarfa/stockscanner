from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from backend.config.strategy_config import DivergenceConfig
from backend.divergence.swing import SwingPoint, find_swing_points


@dataclass(frozen=True)
class DivergenceSignal:
    kind: str  # "bearish" | "bullish" | "hidden_bearish" | "hidden_bullish"
    first_point: SwingPoint
    second_point: SwingPoint
    first_rsi: float
    second_rsi: float
    price_change_pct: float
    rsi_change: float


def _pct_change(a: float, b: float) -> float:
    if a == 0:
        return 0.0
    return (b - a) / abs(a) * 100.0


def detect_divergences(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    rsi_series: pd.Series,
    config: DivergenceConfig,
) -> list[DivergenceSignal]:
    """
    Detects regular and hidden RSI divergence using real swing highs/lows
    (backend.divergence.swing), not a bare current-vs-previous RSI comparison.

    Regular bearish: price higher high, RSI lower high.
    Regular bullish:  price lower low,  RSI higher low.
    Hidden bearish:   price lower high, RSI higher high (trend-continuation short signal).
    Hidden bullish:   price higher low, RSI lower low (trend-continuation long signal).

    A candidate only counts as a confirmed signal once `confirmation_candles`
    bars have printed after the second swing point (so the pivot is not still
    forming at the edge of the available data), and only if it clears both
    `min_price_difference_pct` and `min_rsi_difference`.
    """
    swings = find_swing_points(high, low, config.swing_lookback)
    highs = [p for p in swings if p.kind == "high"]
    lows = [p for p in swings if p.kind == "low"]
    last_index = len(close) - 1

    signals: list[DivergenceSignal] = []

    def rsi_at(point: SwingPoint) -> float | None:
        value = rsi_series.iloc[point.index]
        return None if pd.isna(value) else float(value)

    def confirmed(point: SwingPoint) -> bool:
        return (last_index - point.index) >= config.confirmation_candles

    for points, kinds in ((highs, ("bearish", "hidden_bearish")), (lows, ("bullish", "hidden_bullish"))):
        for a, b in zip(points, points[1:]):
            if not confirmed(b):
                continue
            rsi_a, rsi_b = rsi_at(a), rsi_at(b)
            if rsi_a is None or rsi_b is None:
                continue

            price_diff_pct = _pct_change(a.price, b.price)
            rsi_diff = rsi_b - rsi_a

            if abs(price_diff_pct) < config.min_price_difference_pct:
                continue
            if abs(rsi_diff) < config.min_rsi_difference:
                continue

            regular_kind, hidden_kind = kinds
            if a.kind == "high":
                # Regular bearish: price HH, RSI LH. Hidden bearish: price LH, RSI HH.
                if price_diff_pct > 0 and rsi_diff < 0:
                    kind = regular_kind
                elif price_diff_pct < 0 and rsi_diff > 0:
                    kind = hidden_kind
                else:
                    continue
            else:
                # Regular bullish: price LL, RSI HL. Hidden bullish: price HL, RSI LL.
                if price_diff_pct < 0 and rsi_diff > 0:
                    kind = regular_kind
                elif price_diff_pct > 0 and rsi_diff < 0:
                    kind = hidden_kind
                else:
                    continue

            signals.append(
                DivergenceSignal(
                    kind=kind,
                    first_point=a,
                    second_point=b,
                    first_rsi=rsi_a,
                    second_rsi=rsi_b,
                    price_change_pct=price_diff_pct,
                    rsi_change=rsi_diff,
                )
            )

    return signals


def has_significant_bearish_divergence(signals: list[DivergenceSignal]) -> bool:
    return any(s.kind == "bearish" for s in signals)
