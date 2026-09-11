from __future__ import annotations

from backend.screeners.stock_analysis import StockAnalysisResult
from backend.strategies.types import StrategySignal


def evaluate_strategy_one(result: StockAnalysisResult) -> StrategySignal:
    """
    Thin wrapper exposing the existing Strategy One result (untouched logic
    in backend/screeners/stock_analysis.py) in the same StrategySignal shape
    as the other strategies, so the multi-strategy API can list all six
    uniformly without special-casing the original one.
    """
    qualifies = result.meets_weekly_rsi_band and result.meets_monthly_rsi_min and not result.disqualified_by_divergence
    conditions = {
        "meets_weekly_rsi_band": result.meets_weekly_rsi_band,
        "meets_monthly_rsi_min": result.meets_monthly_rsi_min,
        "not_disqualified_by_divergence": not result.disqualified_by_divergence,
    }
    return StrategySignal(
        strategy="Strategy One",
        symbol=result.symbol,
        sector=result.sector,
        qualifies=qualifies,
        signal_date=result.data_as_of,
        daily_rsi=result.daily.rsi,
        weekly_rsi=result.weekly.rsi,
        monthly_rsi=result.monthly.rsi,
        conditions=conditions,
        explanation="; ".join(result.score.explanation),
        extra={"score": result.score.total_score, "classification": result.score.classification},
    )
