from __future__ import annotations

from pydantic import BaseModel


class ChartCandleOut(BaseModel):
    time: int  # unix seconds (UTC), matches lightweight-charts' UTCTimestamp
    open: float
    high: float
    low: float
    close: float
    volume: float


class ChartCandlesResponse(BaseModel):
    symbol: str
    timeframe: str
    candles: list[ChartCandleOut]
    data_source: str = "ANGEL_ONE"
