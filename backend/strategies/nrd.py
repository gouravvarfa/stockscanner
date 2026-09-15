from __future__ import annotations

from backend.config.multi_strategy_config import NRDConfig
from backend.screeners.stock_analysis import StockAnalysisResult
from backend.strategies.types import StrategySignal, divergence_signal_detail


def evaluate_nrd(result: StockAnalysisResult, config: NRDConfig) -> StrategySignal:
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
         `config.leg_rsi_max` — strict, e.g. leg_rsi_max=30 means both
         legs must be < 30. An older, looser gate on the timeframe's
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
    """
    d, w, m = result.daily.rsi, result.weekly.rsi, result.monthly.rsi

    per_timeframe = (("daily", result.daily), ("weekly", result.weekly), ("monthly", result.monthly))

    conditions: dict[str, bool] = {}
    matches: list[dict] = []
    confirmed_timeframes: list[str] = []

    for timeframe, reading in per_timeframe:
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
        conditions[f"{timeframe}_negative_reversal_structure"] = has_structure
        conditions[f"{timeframe}_leg_rsi_below_max"] = any(
            sig.first_rsi < config.leg_rsi_max and sig.second_rsi < config.leg_rsi_max
            for sig in reading.divergences if sig.kind == "hidden_bearish"
        )
        conditions[f"{timeframe}_fresh_within_lookback"] = confirmed
        conditions[f"{timeframe}_confirmed"] = confirmed
        if confirmed:
            # Only the single freshest (smallest bars_ago) candidate is
            # ever reported — never every fresh pivot in the window.
            candidates.sort(key=lambda c: c["bars_ago"])
            confirmed_timeframes.append(timeframe.upper())
            matches.append(candidates[0])

    qualifies = len(confirmed_timeframes) > 0

    if qualifies:
        best = min(matches, key=lambda c: c["bars_ago"])
        explanation = (
            f"NRD (Negative Reversal) CONFIRMED on {' + '.join(confirmed_timeframes)}: price formed a lower high "
            f"({best['price_change_pct']:+.2f}% vs the prior swing high, bar {best['swing1_bar']} -> {best['swing2_bar']}) "
            f"while RSI formed a higher high (RSI {best['rsi1']:.1f} -> {best['rsi2']:.1f}, both < {config.leg_rsi_max}) "
            f"on {best['timeframe']}, confirmed {best['bars_ago']} bar(s) ago (within the {config.lookback_bars}-bar freshness window)."
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
        extra={"divergences": matches, "divergence_timeframes": confirmed_timeframes, "status": "NRD_CONFIRMED" if qualifies else "NRD_NOT_CONFIRMED"},
    )
