from __future__ import annotations

import pandas as pd

from backend.config.multi_strategy_config import PRDConfig
from backend.config.strategy_config import DEFAULT_STRATEGY_CONFIG
from backend.divergence.swing import find_swing_points
from backend.indicators.resample import to_monthly, to_weekly
from backend.indicators.rsi import rsi
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


def _developing_structures(ohlc: pd.DataFrame, config: PRDConfig, r: pd.Series | None = None) -> list[dict]:
    """
    PRD_FORMING only: B = the latest completed candle, NOT required to be a
    confirmed swing pivot (it cannot be yet — a pivot needs future bars).
    A must be a CONFIRMED historical swing low (existing swing detector, with
    `config.forming_a_pivot_bars` candles on each side — 1 by explicit user
    choice, since the strict 5-bar pivot misses real setups) that
    lies `forming_min_ab_bars`..`forming_max_ab_bars` candles before B (any
    distance in that range is valid). Price higher low + RSI lower low, both
    leg RSIs above the existing `leg_rsi_min`, and the existing divergence
    min price/RSI differences. Never produces a confirmed signal.
    """
    div = DEFAULT_STRATEGY_CONFIG.divergence
    n = len(ohlc)
    if n < 2 * config.forming_a_pivot_bars + 2:
        return []
    r = r if r is not None else rsi(ohlc["close"], period=14)
    b_idx = n - 1
    b_low = float(ohlc["low"].iloc[b_idx])
    b_rsi = r.iloc[b_idx]
    if pd.isna(b_rsi):
        return []
    out: list[dict] = []
    for a in find_swing_points(ohlc["high"], ohlc["low"], config.forming_a_pivot_bars):
        if a.kind != "low":
            continue
        dist = b_idx - a.index
        if not (config.forming_min_ab_bars <= dist <= config.forming_max_ab_bars):
            continue
        a_rsi = r.iloc[a.index]
        if pd.isna(a_rsi):
            continue
        price_pct = (b_low - a.price) / abs(a.price) * 100.0 if a.price else 0.0
        rsi_diff = float(b_rsi) - float(a_rsi)
        if price_pct < div.min_price_difference_pct or rsi_diff > -div.min_rsi_difference:
            continue  # need price higher low AND RSI lower low
        if not (float(a_rsi) > config.leg_rsi_min and float(b_rsi) > config.leg_rsi_min):
            continue
        path = r.iloc[a.index : b_idx + 1]
        if not bool((path > config.leg_rsi_min).all()):
            continue  # RSI must stay above leg_rsi_min for every candle between A and B, not just the endpoints
        out.append({
            "a_date": str(a.date), "a_low": a.price, "a_rsi": float(a_rsi), "a_bar": a.index,
            "b_date": str(ohlc.index[b_idx]), "b_low": b_low, "b_rsi": float(b_rsi), "b_bar": b_idx,
            "ab_distance": dist, "price_change_pct": price_pct, "rsi_change": rsi_diff,
        })
    return out


def _confirmed_reference(ohlc: pd.DataFrame, config: PRDConfig, r: pd.Series | None = None) -> dict | None:
    """
    PRD_CONFIRMED (new definition). A = the LATEST confirmed RSI swing low
    (RSI lower than `confirm_rsi_pivot_bars` bars on each side, so it already
    has that many completed bars after it). Its price low = the lowest LOW
    within +/- `confirm_price_match_window` candles of the RSI pivot - the
    price low need not be on the same candle. B = the latest COMPLETED candle
    (never has to be a pivot). All four must hold:
      A RSI > leg_rsi_min, B RSI > leg_rsi_min, B RSI < A RSI,
      B close > A's price low.
    No breakout candle, freshness, distance, amplitude or B-pivot rule.
    Returns the full comparison (passed or not), or None if there is no RSI
    pivot / not enough data.
    """
    k, win = config.confirm_rsi_pivot_bars, config.confirm_price_match_window
    n = len(ohlc)
    if n < 2 * k + 2:
        return None
    r = r if r is not None else rsi(ohlc["close"], period=14)
    a_idx = None
    for i in range(n - 1 - k, k - 1, -1):  # newest confirmed pivot first
        v = r.iloc[i]
        if pd.isna(v):
            continue
        window = r.iloc[i - k : i + k + 1]
        if v == window.min() and (window == v).sum() == 1:
            a_idx = i
            break
    if a_idx is None:
        return None
    lo, hi = max(0, a_idx - win), min(n - 1, a_idx + win)
    lows = ohlc["low"].iloc[lo : hi + 1]
    p_idx = lo + int(lows.values.argmin())
    b_idx = n - 1
    a_rsi, b_rsi = float(r.iloc[a_idx]), r.iloc[b_idx]
    if pd.isna(b_rsi):
        return None
    b_rsi = float(b_rsi)
    a_low = float(ohlc["low"].iloc[p_idx])
    b_close = float(ohlc["close"].iloc[b_idx])
    path = r.iloc[a_idx : b_idx + 1]
    checks = {
        "a_rsi_above_min": a_rsi > config.leg_rsi_min,
        "b_rsi_above_min": b_rsi > config.leg_rsi_min,
        "rsi_lower_low": b_rsi < a_rsi,
        "price_above_reference_low": b_close > a_low,
        "rsi_stays_above_min_between_legs": bool((path > config.leg_rsi_min).all()),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "reference_rsi_date": str(ohlc.index[a_idx]),
        "reference_rsi": a_rsi,
        "reference_price_low_date": str(ohlc.index[p_idx]),
        "reference_price_low": a_low,
        "current_candle_date": str(ohlc.index[b_idx]),
        "current_close": b_close,
        "current_rsi": b_rsi,
        "rsi_comparison": f"current RSI {b_rsi:.2f} {'<' if b_rsi < a_rsi else '>='} reference RSI {a_rsi:.2f}",
        "price_comparison": f"current close {b_close:.2f} {'>' if b_close > a_low else '<='} reference price low {a_low:.2f}",
        "ref_bar": a_idx, "price_bar": p_idx, "current_bar": b_idx,
    }


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
    forming_details: list[dict] = []
    timeframe_status: dict[str, dict] = {}

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

        # ---- PRD_FORMING (both existing paths, rules untouched) ------------
        tf_rsi = rsi(ohlc["close"], period=14)  # computed once per timeframe, shared by both paths
        developing = _developing_structures(ohlc, config, tf_rsi)

        # ---- PRD_CONFIRMED (new, independent definition) -------------------
        ref = _confirmed_reference(ohlc, config, tf_rsi)
        confirmed = bool(ref and ref["passed"])

        conditions[f"{timeframe}_positive_reversal_structure"] = has_structure
        conditions[f"{timeframe}_leg_rsi_above_min"] = any(
            sig.first_rsi > config.leg_rsi_min and sig.second_rsi > config.leg_rsi_min
            for sig in reading.divergences if sig.kind == "hidden_bullish"
        )
        conditions[f"{timeframe}_fresh_within_lookback"] = structure_ready
        conditions[f"{timeframe}_red_then_green_breakout"] = candle_confirmed
        conditions[f"{timeframe}_developing_b_structure"] = len(developing) > 0
        for name, ok in (ref["checks"] if ref else {}).items():
            conditions[f"{timeframe}_confirm_{name}"] = ok
        conditions[f"{timeframe}_confirmed"] = confirmed

        if developing and not candle_confirmed:
            forming_details.extend({**d_, "timeframe": timeframe, "status": "PRD_FORMING"} for d_ in developing)

        forming_here = (structure_ready and not candle_confirmed) or (developing and not candle_confirmed)
        if forming_here:
            any_forming = True

        if confirmed:
            confirmed_timeframes.append(timeframe.upper())
            price_change_pct = (ref["current_close"] - ref["reference_price_low"]) / ref["reference_price_low"] * 100.0
            matches.append({
                "timeframe": timeframe, "status": "PRD_CONFIRMED",
                "reference_rsi_date": ref["reference_rsi_date"], "reference_rsi": ref["reference_rsi"],
                "reference_price_low_date": ref["reference_price_low_date"], "reference_price_low": ref["reference_price_low"],
                "current_candle_date": ref["current_candle_date"], "current_close": ref["current_close"],
                "current_rsi": ref["current_rsi"],
                "rsi_comparison": ref["rsi_comparison"], "price_comparison": ref["price_comparison"],
                # aliases the dashboard / ranking already read
                "a_date": ref["reference_price_low_date"], "a_low": ref["reference_price_low"],
                "b_date": ref["current_candle_date"], "b_low": ref["current_close"],
                "a_rsi": ref["reference_rsi"], "b_rsi": ref["current_rsi"],
                "rsi1": ref["reference_rsi"], "rsi2": ref["current_rsi"], "bars_ago": 0, "fresh": True,
                "price_change_pct": price_change_pct,
                "ab_distance": ref["current_bar"] - ref["ref_bar"],
            })
        timeframe_status[timeframe] = {
            "status": "PRD_CONFIRMED" if confirmed else ("PRD_FORMING" if forming_here else "PRD_NOT_CONFIRMED"),
            "setups": [] if confirmed else [d_ for d_ in forming_details if d_["timeframe"] == timeframe],
            "reference": ref,
        }

    qualifies = len(confirmed_timeframes) > 0
    status = "PRD_CONFIRMED" if qualifies else ("PRD_FORMING" if any_forming else "PRD_NOT_CONFIRMED")

    if qualifies:
        best = min(matches, key=lambda c: c["ab_distance"])
        explanation = (
            f"PRD CONFIRMED on {' + '.join(confirmed_timeframes)}: reference RSI bottom "
            f"{best['reference_rsi_date'][:10]} (RSI {best['reference_rsi']:.1f}, price low "
            f"{best['reference_price_low']:.2f} on {best['reference_price_low_date'][:10]}); latest completed candle "
            f"{best['current_candle_date'][:10]} has RSI {best['current_rsi']:.1f} (lower) and close "
            f"{best['current_close']:.2f} (above that price low), both RSI readings > {config.leg_rsi_min}."
        )
    elif any_forming and forming_details:
        f = forming_details[0]
        explanation = (
            f"PRD FORMING — developing Positive Reversal on {f['timeframe'].upper()}: confirmed swing low A "
            f"({f['a_date'][:10]}, low {f['a_low']:.2f}, RSI {f['a_rsi']:.1f}) -> latest candle B "
            f"({f['b_date'][:10]}, low {f['b_low']:.2f}, RSI {f['b_rsi']:.1f}), {f['ab_distance']} candles apart: "
            f"price higher low + RSI lower low, both legs > {config.leg_rsi_min}. B is not yet a confirmed pivot."
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
        extra={"divergences": matches, "divergence_timeframes": confirmed_timeframes, "status": status, "forming": forming_details,
            "timeframes": timeframe_status},
    )
