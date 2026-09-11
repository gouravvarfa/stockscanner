from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from backend.config.strategy_config import FibonacciConfig


class ExpiryLevel5Config(BaseModel):
    # Reuses the existing Fibonacci engine's swing/level settings (spec:
    # "do not duplicate indicator logic unnecessarily") rather than a second
    # swing-lookback parameter.
    fibonacci: FibonacciConfig = Field(default_factory=FibonacciConfig)

    # Tolerance band (as a % of the 61.8% level's price) used both to decide
    # whether a candle's low actually "touched" the level, and as the
    # decisive-break threshold below it.
    fib_61_8_tolerance_percent: float = 1.0

    # This is a swing-Fibonacci + candle-confirmation setup, evaluated on
    # daily bars by default (distinct from Expiry Level 1's intraday RSI
    # scalping) — configurable if a shorter-timeframe variant is wanted later.
    timeframe: Literal["FIFTEEN_MINUTE", "ONE_HOUR", "ONE_DAY"] = "ONE_DAY"
    lookback_days: int = 180


DEFAULT_EXPIRY_LEVEL_5_CONFIG = ExpiryLevel5Config()
