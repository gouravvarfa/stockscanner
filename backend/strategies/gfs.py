from __future__ import annotations

from backend.config.multi_strategy_config import GFSConfig
from backend.screeners.stock_analysis import StockAnalysisResult
from backend.strategies.types import StrategySignal


def evaluate_gfs(result: StockAnalysisResult, config: GFSConfig) -> StrategySignal:
    d, w, m = result.daily.rsi, result.weekly.rsi, result.monthly.rsi

    conditions = {
        "daily_rsi_in_band": d is not None and config.daily_min < d < config.daily_max,
        "weekly_rsi_above_min": w is not None and w > config.weekly_min,
        "monthly_rsi_above_min": m is not None and m > config.monthly_min,
    }
    qualifies = all(conditions.values())

    if qualifies:
        explanation = (
            f"GFS qualified: Daily RSI {d:.1f} is between {config.daily_min} and {config.daily_max}, "
            f"Weekly RSI {w:.1f} > {config.weekly_min}, Monthly RSI {m:.1f} > {config.monthly_min}."
        )
    else:
        missing = [k for k, v in conditions.items() if not v]
        explanation = f"GFS not qualified: failed {', '.join(missing) or 'insufficient RSI data'}."

    return StrategySignal(
        strategy="GFS",
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
