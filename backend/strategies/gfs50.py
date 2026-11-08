from __future__ import annotations

from backend.config.multi_strategy_config import Gfs50Config
from backend.screeners.stock_analysis import StockAnalysisResult
from backend.strategies.types import StrategySignal


def evaluate_gfs50(result: StockAnalysisResult, config: Gfs50Config) -> StrategySignal:
    d, w, m = result.daily.rsi, result.weekly.rsi, result.monthly.rsi

    conditions = {
        "daily_rsi_above_min": d is not None and d > config.daily_min,
        "weekly_rsi_above_min": w is not None and w > config.weekly_min,
        "monthly_rsi_above_min": m is not None and m > config.monthly_min,
    }
    qualifies = all(conditions.values())

    if qualifies:
        explanation = (
            f"50 GFS qualified: Daily RSI {d:.1f} > {config.daily_min}, "
            f"Weekly RSI {w:.1f} > {config.weekly_min}, Monthly RSI {m:.1f} > {config.monthly_min}."
        )
    else:
        missing = [k for k, v in conditions.items() if not v]
        explanation = f"50 GFS not qualified: failed {', '.join(missing) or 'insufficient RSI data'}."

    return StrategySignal(
        strategy="50 GFS",
        symbol=result.symbol,
        qualifies=qualifies,
        signal_date=result.data_as_of,
        daily_rsi=d,
        weekly_rsi=w,
        monthly_rsi=m,
        conditions=conditions,
        explanation=explanation,
        extra={
            "previous_daily_rsi": result.daily.previous_rsi,
            "previous_weekly_rsi": result.weekly.previous_rsi,
            "previous_monthly_rsi": result.monthly.previous_rsi,
        },
    )
