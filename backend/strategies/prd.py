from __future__ import annotations

import pandas as pd

from backend.config.multi_strategy_config import PRDConfig
from backend.indicators.resample import to_monthly, to_weekly
from backend.screeners.stock_analysis import StockAnalysisResult
from backend.strategies.types import StrategySignal, divergence_signal_detail


def _candle_confirmation(ohlc: pd.DataFrame) -> tuple[bool, dict | None]:
    """
    Strict PRD candle-confirmation rule (2026-09-13): the last TWO completed
    bars of this timeframe's own OHLC must be RED immediately followed by
    GREEN, with the green bar's close breaking above the red bar's high.
    Both bars are already-completed (the caller only ever passes OHLC whose
    trailing bar is a real closed candle — Angel One's daily/weekly/monthly
    series never includes the still-forming bar). Never uses an unfinished
    candle.
    """
    if len(ohlc) < 2:
        return False, None
    red = ohlc.iloc[-2]
    green = ohlc.iloc[-1]
    is_red = bool(red["close"] < red["open"])
    is_green = bool(green["close"] > green["open"])
    breakout = bool(green["close"] > red["high"])
    confirmed = is_red and is_green and breakout
    detail = {
        "red_open": float(red["open"]), "red_close": float(red["close"]), "red_high": float(red["high"]),
        "green_open": float(green["open"]), "green_close": float(green["close"]),
        "is_red": is_red, "is_green": is_green, "breakout_confirmed": breakout,
    }
    return confirmed, detail


def evaluate_prd(result: StockAnalysisResult, daily_ohlcv: pd.DataFrame, config: PRDConfig) -> StrategySignal:
    """
    PRD = Positive Reversal (price higher low + RSI lower low, at two
    confirmed swing LOWS — backend/divergence/detector.py's "hidden_bullish"
    kind; regular bullish divergence, kind "bullish", must never be
    substituted here). A LATEST-SETUP-ONLY strategy with a mandatory candle
    confirmation, per explicit user direction (2026-09-13). ALL of the
    following must hold on the SAME timeframe for that timeframe to confirm:

      1. A genuine hidden_bullish structure exists (real swing pivots).
      2. BOTH pivot-leg RSI values are above `config.leg_rsi_min` (the
         actual divergence-leg readings, not the timeframe's current RSI).
      3. The confirming pivot occurred within `config.lookback_bars`
         completed bars of the latest bar on that timeframe (freshness).
      4. Candle confirmation: the immediately preceding completed candle on
         that timeframe is RED (close < open), followed by a completed
         GREEN candle (close > open) whose close breaks above the red
         candle's high. Until this candle sequence completes, the setup is
         "FORMING" and does NOT qualify — it is never reported as confirmed
         just because the divergence structure/RSI/freshness already pass.

    Evaluated INDEPENDENTLY on daily/weekly/monthly; qualifies if ANY ONE
    timeframe satisfies all four conditions.
    """
    d, w, m = result.daily.rsi, result.weekly.rsi, result.monthly.rsi

    weekly_df = to_weekly(daily_ohlcv)
    monthly_df = to_monthly(daily_ohlcv)
    per_timeframe = (
        ("daily", result.daily, daily_ohlcv),
        ("weekly", result.weekly, weekly_df),
        ("monthly", result.monthly, monthly_df),
    )

    conditions: dict[str, bool] = {}
    matches: list[dict] = []
    confirmed_timeframes: list[str] = []
    any_forming = False

    for timeframe, reading, ohlc in per_timeframe:
        structure_candidates: list[dict] = []
        for sig in reading.divergences:
            if sig.kind != "hidden_bullish":
                continue
            leg_rsi_ok = sig.first_rsi > config.leg_rsi_min and sig.second_rsi > config.leg_rsi_min
            bars_ago = reading.last_bar_index - sig.second_point.index
            fresh = 0 <= bars_ago <= config.lookback_bars
            if leg_rsi_ok and fresh:
                detail = divergence_signal_detail(sig, timeframe)
                detail["bars_ago"] = bars_ago
                detail["confirmation_bar"] = reading.last_bar_index
                structure_candidates.append(detail)

        has_structure = any(sig.kind == "hidden_bullish" for sig in reading.divergences)
        candle_confirmed, candle_detail = _candle_confirmation(ohlc)

        structure_ready = len(structure_candidates) > 0
        confirmed = structure_ready and candle_confirmed

        conditions[f"{timeframe}_positive_reversal_structure"] = has_structure
        conditions[f"{timeframe}_leg_rsi_above_min"] = any(
            sig.first_rsi > config.leg_rsi_min and sig.second_rsi > config.leg_rsi_min
            for sig in reading.divergences if sig.kind == "hidden_bullish"
        )
        conditions[f"{timeframe}_fresh_within_lookback"] = structure_ready
        conditions[f"{timeframe}_red_then_green_breakout"] = candle_confirmed
        conditions[f"{timeframe}_confirmed"] = confirmed

        if structure_ready and not candle_confirmed:
            any_forming = True

        if confirmed:
            structure_candidates.sort(key=lambda c: c["bars_ago"])
            best = structure_candidates[0]
            best["fresh"] = True
            best["candle"] = candle_detail
            confirmed_timeframes.append(timeframe.upper())
            matches.append(best)

    qualifies = len(confirmed_timeframes) > 0
    status = "PRD_CONFIRMED" if qualifies else ("PRD_FORMING" if any_forming else "PRD_NOT_CONFIRMED")

    if qualifies:
        best = min(matches, key=lambda c: c["bars_ago"])
        explanation = (
            f"PRD (Positive Reversal) CONFIRMED — GREEN BREAKOUT on {' + '.join(confirmed_timeframes)}: price formed "
            f"a higher low ({best['price_change_pct']:+.2f}% vs the prior swing low, bar {best['swing1_bar']} -> "
            f"{best['swing2_bar']}) while RSI formed a lower low (RSI {best['rsi1']:.1f} -> {best['rsi2']:.1f}, both "
            f"> {config.leg_rsi_min}), confirmed {best['bars_ago']} bar(s) ago, and the red-then-green candle "
            f"breakout confirmation has closed."
        )
    elif any_forming:
        explanation = (
            "PRD FORMING — WAITING FOR GREEN CONFIRMATION: a Positive Reversal structure with both RSI legs above "
            f"{config.leg_rsi_min} exists within the latest {config.lookback_bars} bars, but the required red-then-"
            "green candle breakout confirmation has not completed yet."
        )
    else:
        explanation = (
            f"PRD not confirmed: no timeframe had a Positive Reversal (price higher low + RSI lower low, at "
            f"confirmed swing lows) with both pivot-leg RSI values above {config.leg_rsi_min}, confirmed within the "
            f"latest {config.lookback_bars} bars, followed by a red-then-green candle breakout."
        )

    return StrategySignal(
        strategy="PRD",
        symbol=result.symbol,
        qualifies=qualifies,
        signal_date=result.data_as_of,
        daily_rsi=d,
        weekly_rsi=w,
        monthly_rsi=m,
        conditions=conditions,
        explanation=explanation,
        extra={"divergences": matches, "divergence_timeframes": confirmed_timeframes, "status": status},
    )
