"""Shared test helpers for constructing minimal StockAnalysisResult fixtures
without running the full analyze_stock pipeline (isolates strategy-module tests
from indicator/data-fetch concerns)."""
from __future__ import annotations

import pandas as pd

from backend.ranking.scorer import ScoreBreakdown
from backend.screeners.stock_analysis import StockAnalysisResult, TimeframeReading


def make_timeframe(rsi: float | None, divergences: list | None = None, bearish: bool = False) -> TimeframeReading:
    return TimeframeReading(rsi=rsi, divergences=divergences or [], has_bearish_divergence=bearish)


def make_result(
    symbol: str = "TEST",
    sector: str = "Banks",
    daily_rsi: float | None = 50.0,
    weekly_rsi: float | None = 62.0,
    monthly_rsi: float | None = 66.0,
    daily_divergences: list | None = None,
    weekly_divergences: list | None = None,
    monthly_divergences: list | None = None,
) -> StockAnalysisResult:
    score = ScoreBreakdown(
        components={}, weighted={}, total_score=0.0, classification="WEAK SETUP", bias="NEUTRAL", explanation=[]
    )
    return StockAnalysisResult(
        symbol=symbol,
        sector=sector,
        current_price=100.0,
        data_as_of=pd.Timestamp("2024-06-01"),
        daily=make_timeframe(daily_rsi, daily_divergences),
        weekly=make_timeframe(weekly_rsi, weekly_divergences),
        monthly=make_timeframe(monthly_rsi, monthly_divergences),
        fibonacci=None,
        ema20=None,
        ema50=None,
        ema200=None,
        macd_histogram=None,
        adx_value=None,
        volume_ratio_value=None,
        distance_from_52w_high_pct=None,
        meets_weekly_rsi_band=False,
        meets_monthly_rsi_min=False,
        disqualified_by_divergence=False,
        score=score,
    )
