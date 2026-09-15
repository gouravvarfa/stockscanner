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
    cross_status: str
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
    closed candles (the caller — AngelOneProvider.get_intraday_ohlc, via
    drop_incomplete_trailing_bars — already drops any still-forming bar) and
    must be RSI(14) computed by the shared indicator engine
    (backend.indicators.rsi.rsi), not recomputed here.

    A signal requires, at the latest confirmed 15-minute close, ALL of:
    1. Current 15m RSI > rsi_15m_threshold (60 by default).
    2. This is the FIRST confirmed close above that threshold — i.e. the
       immediately preceding confirmed 15m candle's RSI was <= threshold.
       Just being above 60 already (with the previous candle also above 60)
       does NOT re-signal; the setup must first reset by closing back at or
       below 60 before a new cross can fire. Since this is evaluated fresh
       from only the latest two confirmed candles on every scan, "reset" is
       implicit — no persisted state is needed.
    3. Current 1H RSI > rsi_1h_threshold (65 by default), at that same
       15-minute close.
    """
    if len(rsi_15m_series) < 2 or len(rsi_1h_series) < 1:
        return None

    current_15m = rsi_15m_series.iloc[-1]
    previous_15m = rsi_15m_series.iloc[-2]
    current_1h = rsi_1h_series.iloc[-1]

    if pd.isna(current_15m) or pd.isna(previous_15m) or pd.isna(current_1h):
        return None

    is_first_cross = previous_15m <= config.rsi_15m_threshold and current_15m > config.rsi_15m_threshold
    hourly_confirmed = current_1h > config.rsi_1h_threshold

    if not (is_first_cross and hourly_confirmed):
        return None

    cross_status = "FIRST_CROSS_ABOVE_60"
    explanation = (
        f"15-minute RSI made its first confirmed close above {config.rsi_15m_threshold:g} "
        f"(previous {previous_15m:.1f} -> current {current_15m:.1f}) while 1-hour RSI was above "
        f"{config.rsi_1h_threshold:g} (currently {current_1h:.1f})."
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
        cross_status=cross_status,
        status="CONFIRMED",
        explanation=explanation,
    )
