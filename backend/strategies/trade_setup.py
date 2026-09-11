from __future__ import annotations

from dataclasses import dataclass

from backend.screeners.stock_analysis import StockAnalysisResult


@dataclass
class TradeSetup:
    available: bool
    reason: str | None
    entry_low: float | None = None
    entry_high: float | None = None
    stop_loss: float | None = None
    target1: float | None = None
    target2: float | None = None
    risk_reward_t1: float | None = None
    risk_reward_t2: float | None = None
    methodology: str = ""


def calculate_trade_setup(result: StockAnalysisResult) -> TradeSetup:
    """
    Entry: the preferred-zone Fibonacci band around the current price (only
    when price is actually sitting in a preferred retracement zone).
    Stop loss: just below the swing low that defined the Fibonacci swing.
    Targets: the swing high (T1) and a 1.272 extension of the swing range (T2).
    Returns "insufficient data" honestly rather than inventing levels when the
    Fibonacci swing isn't usable or the resulting risk is degenerate.
    """
    fib = result.fibonacci
    if fib is None:
        return TradeSetup(available=False, reason="Insufficient data for reliable level calculation.")

    if not fib.in_preferred_zone:
        return TradeSetup(
            available=False,
            reason="Price is not currently in a preferred Fibonacci retracement zone — Insufficient data for reliable level calculation.",
        )

    entry_low = min(result.current_price, fib.nearest_level.price)
    entry_high = max(result.current_price, fib.nearest_level.price)
    stop_loss = fib.swing_low * 0.995  # small buffer below the swing low
    target1 = fib.swing_high
    swing_range = fib.swing_high - fib.swing_low
    target2 = fib.swing_high + swing_range * 0.272

    risk = entry_high - stop_loss
    if risk <= 0:
        return TradeSetup(available=False, reason="Insufficient data for reliable level calculation.")

    reward1 = target1 - entry_high
    reward2 = target2 - entry_high

    return TradeSetup(
        available=True,
        reason=None,
        entry_low=round(entry_low, 2),
        entry_high=round(entry_high, 2),
        stop_loss=round(stop_loss, 2),
        target1=round(target1, 2),
        target2=round(target2, 2),
        risk_reward_t1=round(reward1 / risk, 2) if reward1 > 0 else None,
        risk_reward_t2=round(reward2 / risk, 2) if reward2 > 0 else None,
        methodology=(
            "Entry zone = current price to nearest Fibonacci retracement level "
            f"({fib.nearest_level.ratio:.3f}). Stop loss = swing low minus 0.5% buffer. "
            "Target 1 = swing high. Target 2 = swing high + 27.2% extension of the swing range."
        ),
    )
