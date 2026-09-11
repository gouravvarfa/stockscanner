"""
Configuration for the additional strategies (GFS, Advanced GFS, PRD, NRD,
Value Buy). Deliberately separate from backend/config/strategy_config.py
(Strategy One) so tuning these can never affect Strategy One's behavior.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class GFSConfig(BaseModel):
    daily_min: float = 38.0
    daily_max: float = 45.0
    weekly_min: float = 60.0
    monthly_min: float = 60.0


class AdvancedGFSConfig(BaseModel):
    daily_min: float = 59.0
    daily_max: float = 65.0
    weekly_min: float = 65.0
    monthly_min: float = 68.0


class PRDConfig(BaseModel):
    """
    PRD (Positive Reverse Divergence) is confirmed in an UPTREND context —
    real bullish divergence (price lower low, RSI higher low) found while
    D/W/M RSI is ABOVE a floor. Gate is a RSI FLOOR, not a ceiling — using
    the same ">60" gate as NRD (as an earlier version of this project did,
    following the original spec literally) let a single stock satisfy both
    PRD and NRD simultaneously, which is wrong. This floor/ceiling split
    (PRD=floor, NRD=ceiling) makes PRD and NRD mutually exclusive by
    construction, per explicit user direction: PRD = up/uptrend, NRD =
    down/downtrend.
    """
    daily_min: float = 60.0
    weekly_min: float = 60.0
    monthly_min: float = 60.0


class NRDConfig(BaseModel):
    """
    NRD (Negative Reverse Divergence) is confirmed in a DOWNTREND context —
    real bearish divergence (price higher high, RSI lower high) found while
    D/W/M RSI is BELOW a ceiling. Gate is a RSI CEILING (all three
    timeframes below it); see PRDConfig's docstring for why this differs
    from PRD's floor gate.
    """
    daily_max: float = 45.0
    weekly_max: float = 45.0
    monthly_max: float = 45.0


class ValueBuyConfig(BaseModel):
    monthly_rsi_support_min: float = 35.0
    monthly_rsi_support_max: float = 45.0
    trendline_swing_lookback: int = 5


class MultiStrategyConfig(BaseModel):
    gfs: GFSConfig = Field(default_factory=GFSConfig)
    advanced_gfs: AdvancedGFSConfig = Field(default_factory=AdvancedGFSConfig)
    prd: PRDConfig = Field(default_factory=PRDConfig)
    nrd: NRDConfig = Field(default_factory=NRDConfig)
    value_buy: ValueBuyConfig = Field(default_factory=ValueBuyConfig)


DEFAULT_MULTI_STRATEGY_CONFIG = MultiStrategyConfig()
