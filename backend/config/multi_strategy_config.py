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
    PRD (Positive Reversal Divergence) = a genuine Positive Reversal (price
    higher low + RSI lower low, at two confirmed swing lows — see
    backend/strategies/prd.py) whose BOTH pivot-leg RSI values (not the
    current/latest RSI) are above `leg_rsi_min`, whose confirming pivot
    occurred within `lookback_bars` completed bars of now, AND whose candle
    sequence shows a RED bar immediately followed by a GREEN breakout bar
    (green close > red high) — both bars fully completed. Per explicit user
    direction (2026-09-13): strict thresholds, no substitution.
    """
    leg_rsi_min: float = 60.0
    lookback_bars: int = 7


class NRDConfig(BaseModel):
    """
    NRD (Negative Reversal Divergence) = a genuine Negative Reversal (price
    lower high + RSI higher high, at two confirmed swing highs — see
    backend/strategies/nrd.py) whose BOTH pivot-leg RSI values are below
    `leg_rsi_max`, and whose confirming pivot occurred within
    `lookback_bars` completed bars of now. Per explicit user direction
    (2026-09-13): strict thresholds, no substitution.
    """
    leg_rsi_max: float = 30.0
    lookback_bars: int = 7


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
