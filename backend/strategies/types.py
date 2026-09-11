from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from backend.divergence.detector import DivergenceSignal


def divergence_signal_detail(sig: DivergenceSignal, timeframe: str) -> dict:
    return {
        "timeframe": timeframe,
        "swing1_date": sig.first_point.date,
        "swing1_price": sig.first_point.price,
        "swing2_date": sig.second_point.date,
        "swing2_price": sig.second_point.price,
        "rsi1": sig.first_rsi,
        "rsi2": sig.second_rsi,
        "price_change_pct": sig.price_change_pct,
        "rsi_change": sig.rsi_change,
    }


@dataclass
class StrategySignal:
    strategy: str
    symbol: str
    sector: str
    qualifies: bool
    signal_date: pd.Timestamp | None
    daily_rsi: float | None
    weekly_rsi: float | None
    monthly_rsi: float | None
    conditions: dict[str, bool]
    explanation: str
    extra: dict[str, Any] = field(default_factory=dict)
