from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from backend.config.expiry_level_1_config import ExpiryLevel1Config


@dataclass
class ExpiryLevel1Signal:
    symbol: str
    instrument_type: str  # "INDEX" | "STOCK"
    name: str
    sector: str | None
    signal_date: pd.Timestamp
    rsi_15m: float
    rsi_15m_prev: float
    rsi_1h: float
    status: str
    explanation: str


def detect_expiry_level_1_signal(
    symbol: str,
    instrument_type: str,
    name: str,
    sector: str | None,
    rsi_15m_series: pd.Series,
    rsi_1h_series: pd.Series,
    config: ExpiryLevel1Config,
) -> ExpiryLevel1Signal | None:
    """
    `rsi_15m_series` and `rsi_1h_series` must be built from ONLY confirmed/
    closed candles (the caller — AngelOneProvider.get_intraday_ohlc — already
    drops any still-forming bar) and must be RSI(14) computed by the shared
    indicator engine (backend.indicators.rsi.rsi), not recomputed here.

    A signal requires, at the latest confirmed 15-minute close:
    1. Current 15m RSI inside the [rsi_15m_min, rsi_15m_max] band (58-65 by
       default) — a momentum-building zone, not yet overbought.
    2. Current 1H RSI above rsi_1h_threshold (65) — the higher timeframe
       already confirms strength.
    """
    if len(rsi_15m_series) < 1 or len(rsi_1h_series) < 1:
        return None

    current_15m = rsi_15m_series.iloc[-1]
    previous_15m = rsi_15m_series.iloc[-2] if len(rsi_15m_series) >= 2 else float("nan")
    current_1h = rsi_1h_series.iloc[-1]

    if pd.isna(current_15m) or pd.isna(current_1h):
        return None

    band_confirmed = config.rsi_15m_min <= current_15m <= config.rsi_15m_max
    hourly_confirmed = current_1h > config.rsi_1h_threshold

    if not (band_confirmed and hourly_confirmed):
        return None

    explanation = (
        f"15-minute RSI is inside the {config.rsi_15m_min:g}-{config.rsi_15m_max:g} band "
        f"(currently {current_15m:.1f}) while 1-hour RSI is above {config.rsi_1h_threshold:g} "
        f"(currently {current_1h:.1f})."
    )

    return ExpiryLevel1Signal(
        symbol=symbol,
        instrument_type=instrument_type,
        name=name,
        sector=sector,
        signal_date=rsi_15m_series.index[-1],
        rsi_15m=float(current_15m),
        rsi_15m_prev=float(previous_15m),
        rsi_1h=float(current_1h),
        status="CONFIRMED",
        explanation=explanation,
    )
