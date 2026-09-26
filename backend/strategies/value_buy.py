from __future__ import annotations
import pandas as pd
from backend.config.multi_strategy_config import ValueBuyConfig
from backend.indicators.resample import to_weekly
from backend.screeners.stock_analysis import StockAnalysisResult
from backend.strategies.types import StrategySignal
from backend.trendlines.engine import detect_key_reversal, detect_trendline_breakout


def evaluate_value_buy(
    result: StockAnalysisResult, daily_ohlcv: pd.DataFrame, config: ValueBuyConfig
) -> StrategySignal:
    d, w, m = result.daily.rsi, result.weekly.rsi, result.monthly.rsi

    weekly_df = to_weekly(daily_ohlcv)
    weekly_green = False
    if len(weekly_df) >= 1:
        last_week = weekly_df.iloc[-1]
        weekly_green = bool(last_week["close"] > last_week["open"])

    # 2026-09-26 (master RSI-freshness change): `result.monthly.rsi` is now
    # the LATEST/LIVE monthly RSI — it already includes the current
    # still-forming month (see analyze_stock's live_monthly_df) instead of
    # stopping at the last fully completed month. No separate "live month"
    # logic needed here any more: the support-zone check just reads the
    # (now live) value stock_analysis.py already computed, same as every
    # other strategy. Current month candle colour is irrelevant here (both
    # RED and GREEN are allowed) — only the weekly candle's colour matters,
    # per the existing (unchanged) weekly condition below.
    monthly_in_support = m is not None and config.monthly_rsi_support_min <= m <= config.monthly_rsi_support_max

    key_reversal = detect_key_reversal(daily_ohlcv)
    trendline_breakout = detect_trendline_breakout(daily_ohlcv, config.trendline_swing_lookback)
    daily_trigger = key_reversal.detected or trendline_breakout.detected

    conditions = {
        "monthly_rsi_in_support_zone": monthly_in_support,
        "latest_confirmed_weekly_candle_green": weekly_green,
        "key_reversal_or_trendline_breakout": daily_trigger,
    }
    qualifies = all(conditions.values())

    if qualifies:
        trigger_desc = "a key reversal" if key_reversal.detected else "a trendline breakout"
        explanation = (
            f"Value Buy qualified: latest monthly RSI {m:.1f} is in the "
            f"{config.monthly_rsi_support_min}-{config.monthly_rsi_support_max} support zone, "
            f"the latest confirmed weekly candle closed green, and the daily chart confirmed {trigger_desc}."
        )
    else:
        missing = [k for k, v in conditions.items() if not v]
        explanation = f"Value Buy not qualified: failed {', '.join(missing)}."

    return StrategySignal(
        strategy="Value Buy",
        symbol=result.symbol,
        qualifies=qualifies,
        signal_date=result.data_as_of,
        daily_rsi=d,
        weekly_rsi=w,
        monthly_rsi=m,
        conditions=conditions,
        explanation=explanation,
        extra={
            "key_reversal_detected": key_reversal.detected,
            "trendline_breakout_detected": trendline_breakout.detected,
            "trendline_breakout_price": trendline_breakout.breakout_price,
            "trendline_price_at_breakout": trendline_breakout.trendline_price_at_breakout,
            "previous_daily_rsi": result.daily.previous_rsi,
            "previous_weekly_rsi": result.weekly.previous_rsi,
            "previous_monthly_rsi": result.monthly.previous_rsi,
        },
    )
