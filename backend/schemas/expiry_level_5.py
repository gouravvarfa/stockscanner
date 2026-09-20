from __future__ import annotations

import datetime as dt

from pydantic import BaseModel

from backend.schemas.instrument import FnoTyped


class CandleOut(BaseModel):
    open: float
    high: float
    low: float
    close: float


class ExpiryLevel5SignalOut(FnoTyped):
    strategy: str = "EXPIRY_LEVEL_5"
    signal: str = "BUY_CE"
    symbol: str
    instrument_type: str = "STOCK_FUTURE"
    signal_date: dt.datetime
    swing_high: float
    swing_low: float
    fib_38_2: float | None
    fib_50: float | None
    fib_61_8: float
    support_price: float
    support_confirmed: bool
    confirmation_candle: CandleOut
    previous_candle_high: float
    confirmation_close_above_previous_high: bool
    reason: str


class ExpiryLevel5ResultOut(BaseModel):
    started_at: dt.datetime
    finished_at: dt.datetime
    execution_seconds: float
    angelone_configured: bool
    symbols_scanned: int
    symbols_failed: int
    failed_symbols: list[str]
    signals: list[ExpiryLevel5SignalOut]
    data_source_summary: dict[str, int] = {}
    errors: list[str]
