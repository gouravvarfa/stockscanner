from __future__ import annotations

from pydantic import BaseModel


class ExpiryLevel1Config(BaseModel):
    rsi_15m_min: float = 58.0
    rsi_15m_max: float = 65.0
    rsi_1h_threshold: float = 65.0
    rsi_period: int = 14
    intraday_lookback_days: int = 5


DEFAULT_EXPIRY_LEVEL_1_CONFIG = ExpiryLevel1Config()
