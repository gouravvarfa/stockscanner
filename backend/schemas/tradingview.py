from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field, field_validator

VALID_STRATEGIES = {"Strategy One", "GFS", "Advanced GFS", "PRD", "NRD", "Value Buy", "SECTOR_RSI"}
VALID_DIVERGENCE_TYPES = {"PRD", "NRD"}

# SECTOR_RSI is a distinct kind of TradingView signal from the six stock
# strategies above: it carries a sector/NSE-index's own D/W/M RSI (e.g.
# symbol="Nifty Healthcare"), used only as an optional fallback data source
# for backend/sector_analysis/engine.py when Tapetide/Angel One can't supply
# weekly/monthly sector RSI. It never feeds stock-level strategy signals.


class TradingViewWebhookPayload(BaseModel):
    """
    Shape of the JSON body a TradingView alert sends to
    POST /api/tradingview/webhook. Extra PRD/NRD/Value Buy fields are
    optional and only required for their respective strategies (validated
    in backend/services/tradingview_service.py, not here, so the error
    message can name exactly which field is missing for which strategy).
    """

    source: Literal["tradingview"]
    symbol: str = Field(min_length=1)
    exchange: str | None = None
    strategy: str
    timeframe: str = Field(min_length=1)
    signal_date: dt.datetime
    daily_rsi: float | None = None
    weekly_rsi: float | None = None
    monthly_rsi: float | None = None
    signal: bool

    # PRD / NRD only
    divergence_type: str | None = None
    divergence_timeframe: str | None = None

    # Value Buy only
    weekly_candle: str | None = None
    daily_trigger: str | None = None

    @field_validator("strategy")
    @classmethod
    def _strategy_must_be_known(cls, v: str) -> str:
        if v not in VALID_STRATEGIES:
            raise ValueError(f"Unknown strategy '{v}'. Must be one of {sorted(VALID_STRATEGIES)}.")
        return v

    @field_validator("divergence_type")
    @classmethod
    def _divergence_type_must_be_known(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_DIVERGENCE_TYPES:
            raise ValueError(f"Unknown divergence_type '{v}'. Must be one of {sorted(VALID_DIVERGENCE_TYPES)}.")
        return v


class TradingViewWebhookResponse(BaseModel):
    success: bool
    message: str
    signal_id: str | None = None
    strategy: str | None = None
    symbol: str | None = None


class TradingViewSignalOut(BaseModel):
    id: int
    source: str
    symbol: str
    exchange: str | None
    strategy: str
    signal_timeframe: str
    signal_date: dt.datetime
    daily_rsi: float | None
    weekly_rsi: float | None
    monthly_rsi: float | None
    divergence_type: str | None
    divergence_timeframe: str | None
    trigger: str | None
    received_at: dt.datetime
    status: str

    model_config = {"from_attributes": True}


class TradingViewStatusOut(BaseModel):
    enabled: bool
    configured: bool  # enabled AND a secret is set
    signal_count: int
    latest_signal_at: dt.datetime | None
