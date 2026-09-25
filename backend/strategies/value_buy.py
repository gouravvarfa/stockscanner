from __future__ import annotations
import pandas as pd
from backend.config.multi_strategy_config import ValueBuyConfig
from backend.indicators.resample import to_monthly, to_weekly
from backend.indicators.rsi import rsi
from backend.screeners.stock_analysis import StockAnalysisResult
from backend.strategies.types import StrategySignal
from backend.trendlines.engine import detect_key_reversal, detect_trendline_breakout

LIVE_MONTH_RSI_LOW = 38.0
LIVE_MONTH_RSI_HIGH = 45.0


def _live_month_rsi(daily_ohlcv: pd.DataFrame) -> tuple[float | None, float | None, bool]:
    """(live RSI at current price, live RSI at the month's high, current month green)."""
    monthly = to_monthly(daily_ohlcv, include_partial=True)
    if len(monthly) < 15:
        return None, None, False
    last = monthly.iloc[-1]
    closes = monthly["close"].astype(float)
    live = float(rsi(closes, 14).iloc[-1])
    peak_closes = closes.copy()
    peak_closes.iloc[-1] = float(last["high"])
    peak = float(rsi(peak_closes, 14).iloc[-1])
    return live, max(live, peak), bool(last["close"] > last["open"])


def evaluate_value_buy(
    result: StockAnalysisResult, daily_ohlcv: pd.DataFrame, config: ValueBuyConfig
) -> StrategySignal:
    d, w, m = result.daily.rsi, result.weekly.rsi, result.monthly.rsi

    weekly_df = to_weekly(daily_ohlcv)
    weekly_green = False
    if len(weekly_df) >= 1:
        last_week = weekly_df.iloc[-1]
        weekly_green = bool(last_week["close"] > last_week["open"])

    # LIVE MONTH rule (final): use the current, still-forming monthly
    # candle. Passes when that candle is green (price > month open) AND
    # the live monthly RSI peak (approximated using the month's HIGH as
    # the close) falls inside the 38-45 zone. This upper bound is
    # intentional — it keeps overbought names (RSI 50/60/70+) out of
    # Value Buy. Same RSI formula; only the input series differs.
    live = _live_month_rsi(daily_ohlcv)
    live_rsi, live_rsi_peak, live_month_green = live
    monthly_in_support = (
        live_month_green
        and live_rsi_peak is not None
        and LIVE_MONTH_RSI_LOW <= live_rsi_peak <= LIVE_MONTH_RSI_HIGH
    )

    key_reversal = detect_key_reversal(daily_ohlcv)
    trendline_breakout = detect_trendline_breakout(daily_ohlcv, config.trendline_swing_lookback)
    daily_trigger = key_reversal.detected or trendline_breakout.detected

    conditions = {
        "live_month_green_and_rsi_in_38_45_zone": monthly_in_support,
        "latest_confirmed_weekly_candle_green": weekly_green,
        "key_reversal_or_trendline_breakout": daily_trigger,
    }
    qualifies = all(conditions.values())

    if qualifies:
        trigger_desc = "a key reversal" if key_reversal.detected else "a trendline breakout"
        explanation = (
            f"Value Buy qualified (LIVE MONTH): current month candle is green and live monthly RSI "
            f"peak is {live_rsi_peak:.1f} (within {LIVE_MONTH_RSI_LOW}-{LIVE_MONTH_RSI_HIGH}, "
            f"now {live_rsi:.1f}), the latest confirmed weekly candle closed green, and the daily "
            f"chart confirmed {trigger_desc}."
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
            "live_month": True,
            "live_monthly_rsi": live_rsi,
            "live_monthly_rsi_peak": live_rsi_peak,
            "live_month_green": live_month_green,
            "confirmed_monthly_rsi": m,
        },
    )