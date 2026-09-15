"""
Strategy configuration for the NIFTY 200 scanner.

All thresholds and weights are deliberately editable here rather than
hardcoded inline in the screener/scoring engine (spec section 30).
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class StockRSIConfig(BaseModel):
    weekly_min: float = 60.0
    weekly_max: float = 65.0
    monthly_min: float = 65.0
    # Daily RSI is a confirmation factor only, not a hard filter (spec section 8).
    daily_confirmation_enabled: bool = False
    daily_min: float = 0.0
    daily_max: float = 100.0


class DivergenceConfig(BaseModel):
    swing_lookback: int = 5
    min_price_difference_pct: float = 0.5
    min_rsi_difference: float = 2.0
    confirmation_candles: int = 2
    # If True, ANY confirmed bearish divergence (daily/weekly/monthly) disqualifies the stock.
    strict_mode: bool = False


class FibonacciConfig(BaseModel):
    levels: list[float] = Field(default_factory=lambda: [0.236, 0.382, 0.5, 0.618, 0.786])
    preferred_zones: list[float] = Field(default_factory=lambda: [0.382, 0.5, 0.618])
    zone_tolerance_pct: float = 1.5
    swing_lookback_bars: int = 90


class TrendConfig(BaseModel):
    ema_fast: int = 20
    ema_medium: int = 50
    ema_slow: int = 200
    adx_period: int = 14
    adx_healthy_min: float = 20.0
    volume_avg_period: int = 20
    volume_ratio_min: float = 1.0


class ScoringWeights(BaseModel):
    # Sector-based components (sector_outperformance, sector_rsi) were
    # removed along with the rest of the sector system — the scanner now
    # runs entirely on stock-level Angel One data, no sector index at all.
    # compute_score() (backend/ranking/scorer.py) normalizes by the
    # configured weight total, so removing them simply redistributes their
    # share across the remaining components rather than leaving a scoring
    # gap.
    stock_rsi: float = 20.0
    divergence: float = 15.0
    fibonacci: float = 10.0
    trend: float = 5.0
    volume: float = 5.0
    macd_adx: float = 5.0

    def total(self) -> float:
        return self.stock_rsi + self.divergence + self.fibonacci + self.trend + self.volume + self.macd_adx


class ClassificationThresholds(BaseModel):
    strong_setup_min: float = 90.0
    good_setup_min: float = 80.0
    moderate_setup_min: float = 70.0


class StrategyConfig(BaseModel):
    stock_rsi: StockRSIConfig = Field(default_factory=StockRSIConfig)
    divergence: DivergenceConfig = Field(default_factory=DivergenceConfig)
    fibonacci: FibonacciConfig = Field(default_factory=FibonacciConfig)
    trend: TrendConfig = Field(default_factory=TrendConfig)
    weights: ScoringWeights = Field(default_factory=ScoringWeights)
    classification: ClassificationThresholds = Field(default_factory=ClassificationThresholds)


DEFAULT_STRATEGY_CONFIG = StrategyConfig()
