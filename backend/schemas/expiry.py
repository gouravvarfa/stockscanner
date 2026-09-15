from __future__ import annotations

import datetime as dt

from pydantic import BaseModel


class ExpiryLevel1SignalOut(BaseModel):
    symbol: str
    instrument_type: str
    name: str
    sector: str | None
    signal_date: dt.datetime
    rsi_15m: float
    rsi_15m_prev: float
    rsi_1h: float
    status: str
    strategy: str = "Expiry Level 1"
    explanation: str


class ExpiryLevel1ResultOut(BaseModel):
    started_at: dt.datetime
    finished_at: dt.datetime
    execution_seconds: float
    angelone_configured: bool
    symbols_scanned: int
    symbols_failed: int
    failed_symbols: list[str]
    index_signals: list[ExpiryLevel1SignalOut]
    stock_signals: list[ExpiryLevel1SignalOut]
    data_source_summary: dict[str, int] = {}
    errors: list[str]
