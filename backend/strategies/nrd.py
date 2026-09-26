from __future__ import annotations

import pandas as pd

from backend.config.multi_strategy_config import NRDConfig
from backend.config.strategy_config import DEFAULT_STRATEGY_CONFIG
from backend.divergence.swing import find_swing_points
from backend.indicators.resample import to_monthly, to_weekly
from backend.indicators.rsi import rsi
from backend.screeners.stock_analysis import StockAnalysisResult
from backend.strategies.types import StrategySignal, divergence_signal_detail


def _developing_structures(ohlc: pd.DataFrame, config: NRDConfig, r: pd.Series | None = None) -> list[dict]:
    """
    NRD_FORMING (mirrors PRD's `_developing_structures`, inverted for the
    bearish case): B = the latest completed candle, NOT required to be a
    confirmed swing pivot. A must be a CONFIRMED historical swing HIGH
    (`config.forming_a_pivot_bars` candles each side) lying
    `forming_min_ab_bars`..`forming_max_ab_bars` candles before B. Price
    lower high + RSI higher high, both leg RSIs below `leg_rsi_max`, and
    RSI must stay below `leg_rsi_max` for every candle between A and B (not
    just the two endpoints — same fix applied to PRD on 2026-09-22). Never
    produces a confirmed signal.
    """
    div = DEFAULT_STRATEGY_CONFIG.divergence
    n = len(ohlc)
    if n < 2 * config.forming_a_pivot_bars + 2:
        return []
    r = r if r is not None else rsi(ohlc["close"], period=14)
    b_idx = n - 1
    b_high = float(ohlc["high"].iloc[b_idx])
    b_rsi = r.iloc[b_idx]
    if pd.isna(b_rsi):
        return []
    out: list[dict] = []
    for a in find_swing_points(ohlc["high"], ohlc["low"], config.forming_a_pivot_bars):
        if a.kind != "high":
            continue
        dist = b_idx - a.index
        if not (config.forming_min_ab_bars <= dist <= config.forming_max_ab_bars):
            continue
        a_rsi = r.iloc[a.index]
        if pd.isna(a_rsi):
            continue
        price_pct = (a.price - b_high) / abs(a.price) * 100.0 if a.price else 0.0
        rsi_diff = float(b_rsi) - float(a_rsi)
        if price_pct < div.min_price_difference_pct or rsi_diff < div.min_rsi_difference:
            continue  # need price lower high AND RSI higher high
        if not (float(a_rsi) < config.leg_rsi_max and float(b_rsi) < config.leg_rsi_max):
            continue
        path = r.iloc[a.index : b_idx + 1]
        if not bool((path < config.leg_rsi_max).all()):
            continue  # RSI must stay below leg_rsi_max for every candle between A and B, not just the endpoints
        out.append({
            "a_date": str(a.date), "a_high": a.price, "a_rsi": float(a_rsi), "a_bar": a.index,
            "b_date": str(ohlc.index[b_idx]), "b_high": b_high, "b_rsi": float(b_rsi), "b_bar": b_idx,
            "ab_distance": dist, "price_change_pct": -price_pct, "rsi_change": rsi_diff,
        })
    return out


def evaluate_nrd(result: StockAnalysisResult, daily_ohlcv: pd.DataFrame, config: NRDConfig) -> StrategySignal:
    """
    NRD = Negative Reversal (price lower high + RSI higher high, at two
    confirmed swing HIGHS — backend/divergence/detector.py's "hidden_bearish"
    kind; regular bearish divergence, kind "bearish", must never be
    substituted here). A LATEST-SETUP-ONLY strategy per explicit user
    direction (2026-09-13): a candidate qualifies only when ALL of these
    hold, evaluated on the confirming (second) pivot leg:

      1. A genuine hidden_bearish structure exists (real swing pivots, no
         approximation/lookahead — see backend/divergence/swing.py).
      2. BOTH pivot-leg RSI values (not the current/latest RSI) are below
         `config.leg_rsi_max` — strict, e.g. leg_rsi_max=40 means both
         legs must be < 40. An older, looser gate on the timeframe's
         *current* RSI is not used; the two actual divergence-leg RSI
         readings are what get checked.
      3. The confirming pivot occurred within `config.lookback_bars`
         completed bars of the latest bar on that timeframe (freshness) —
         an old divergence is never returned just because both pivots are
         still visible on the chart.

    Evaluated INDEPENDENTLY on daily/weekly/monthly; qualifies if ANY ONE
    timeframe confirms. Only the single MOST RECENT valid setup per
    timeframe is ever reported — if several fresh pivots exist within the
    lookback window, older ones (even though still "fresh") are dropped in
    favor of the freshest, per explicit user direction (2026-09-13): "Output
    me sirf most recent valid PRD/NRD setup dikhao."

    NRD_FORMING (2026-09-22, mirrors PRD_FORMING): on any timeframe where B
    (the latest completed candle, not yet a confirmed pivot) is developing a
    Negative Reversal against a confirmed swing-high A, but hasn't itself
    become a confirmed pivot/fresh setup yet, the timeframe is reported as
    "developing" — same two-path model as PRD (see backend/strategies/prd.py).
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
        candidates: list[dict] = []
        for sig in reading.divergences:
            if sig.kind != "hidden_bearish":
                continue
            leg_rsi_ok = sig.first_rsi < config.leg_rsi_max and sig.second_rsi < config.leg_rsi_max
            bars_ago = reading.last_bar_index - sig.second_point.index
            fresh = 0 <= bars_ago <= config.lookback_bars
            if leg_rsi_ok and fresh:
                detail = divergence_signal_detail(sig, timeframe)
                detail["bars_ago"] = bars_ago
                detail["confirmation_bar"] = reading.last_bar_index
                detail["fresh"] = True
                candidates.append(detail)

        has_structure = any(sig.kind == "hidden_bearish" for sig in reading.divergences)
        confirmed = len(candidates) > 0

        tf_rsi = rsi(ohlc["close"], period=14)  # computed once per timeframe, shared by the forming check
        developing = _developing_structures(ohlc, config, tf_rsi)

        conditions[f"{timeframe}_negative_reversal_structure"] = has_structure
        conditions[f"{timeframe}_leg_rsi_below_max"] = any(
            sig.first_rsi < config.leg_rsi_max and sig.second_rsi < config.leg_rsi_max
            for sig in reading.divergences if sig.kind == "hidden_bearish"
        )
        conditions[f"{timeframe}_fresh_within_lookback"] = confirmed
        conditions[f"{timeframe}_confirmed"] = confirmed
        conditions[f"{timeframe}_developing_b_structure"] = len(developing) > 0

        if developing and not confirmed:
            forming_details.extend({**d_, "timeframe": timeframe, "status": "NRD_FORMING"} for d_ in developing)

        forming_here = developing and not confirmed
        if forming_here:
            any_forming = True

        if confirmed:
            # Only the single freshest (smallest bars_ago) candidate is
            # ever reported — never every fresh pivot in the window.
            candidates.sort(key=lambda c: c["bars_ago"])
            confirmed_timeframes.append(timeframe.upper())
            matches.append(candidates[0])

        timeframe_status[timeframe] = {
            "status": "NRD_CONFIRMED" if confirmed else ("NRD_FORMING" if forming_here else "NRD_NOT_CONFIRMED"),
            "setups": [] if confirmed else [d_ for d_ in forming_details if d_["timeframe"] == timeframe],
        }

    qualifies = len(confirmed_timeframes) > 0
    status = "NRD_CONFIRMED" if qualifies else ("NRD_FORMING" if any_forming else "NRD_NOT_CONFIRMED")

    if qualifies:
        best = min(matches, key=lambda c: c["bars_ago"])
        explanation = (
            f"NRD (Negative Reversal) CONFIRMED on {' + '.join(confirmed_timeframes)}: price formed a lower high "
            f"({best['price_change_pct']:+.2f}% vs the prior swing high, bar {best['swing1_bar']} -> {best['swing2_bar']}) "
            f"while RSI formed a higher high (RSI {best['rsi1']:.1f} -> {best['rsi2']:.1f}, both < {config.leg_rsi_max}) "
            f"on {best['timeframe']}, confirmed {best['bars_ago']} bar(s) ago (within the {config.lookback_bars}-bar freshness window)."
        )
    elif any_forming and forming_details:
        f = forming_details[0]
        explanation = (
            f"NRD FORMING — developing Negative Reversal on {f['timeframe'].upper()}: confirmed swing high A "
            f"({f['a_date'][:10]}, high {f['a_high']:.2f}, RSI {f['a_rsi']:.1f}) -> latest candle B "
            f"({f['b_date'][:10]}, high {f['b_high']:.2f}, RSI {f['b_rsi']:.1f}), {f['ab_distance']} candles apart: "
            f"price lower high + RSI higher high, both legs < {config.leg_rsi_max}. B is not yet a confirmed pivot."
        )
    else:
        explanation = (
            f"NRD not confirmed: no timeframe had a Negative Reversal (price lower high + RSI higher high, at "
            f"confirmed swing highs) with both pivot-leg RSI values below {config.leg_rsi_max} AND confirmed within "
            f"the latest {config.lookback_bars} bars."
        )

    return StrategySignal(
        strategy="NRD",
        symbol=result.symbol,
        qualifies=qualifies,
        signal_date=result.data_as_of,
        daily_rsi=d,
        weekly_rsi=w,
        monthly_rsi=m,
        conditions=conditions,
        explanation=explanation,
        extra={
            "divergences": matches, "divergence_timeframes": confirmed_timeframes, "status": status,
            "forming": forming_details, "timeframes": timeframe_status,
            "previous_daily_rsi": result.daily.previous_rsi,
            "previous_weekly_rsi": result.weekly.previous_rsi,
            "previous_monthly_rsi": result.monthly.previous_rsi,
        },
    )
