from __future__ import annotations

from backend.config.multi_strategy_config import NRDConfig
from backend.screeners.stock_analysis import StockAnalysisResult
from backend.strategies.types import StrategySignal, divergence_signal_detail


def evaluate_nrd(result: StockAnalysisResult, config: NRDConfig) -> StrategySignal:
    """
    NRD (Negative Reverse Divergence) = a genuine bearish RSI divergence
    (price makes a higher high while RSI makes a lower high — real swing
    points), evaluated INDEPENDENTLY on each of daily/weekly/monthly. A
    timeframe confirms NRD only when BOTH a bearish divergence exists on
    that timeframe AND that same timeframe's own RSI is below its ceiling
    (a downtrend context) — the divergence timeframe and the RSI timeframe
    are never cross-coupled, so a missing or failing RSI on one timeframe
    can never block a different timeframe that already confirms on its
    own. The stock qualifies for NRD if ANY ONE (or more) of the three
    timeframes confirms — not all three at once. PRD uses the opposite
    (floor) gate, so a stock can never match both on the same timeframe.
    """
    d, w, m = result.daily.rsi, result.weekly.rsi, result.monthly.rsi

    per_timeframe = (
        ("daily", result.daily, config.daily_max),
        ("weekly", result.weekly, config.weekly_max),
        ("monthly", result.monthly, config.monthly_max),
    )

    conditions: dict[str, bool] = {}
    matches: list[dict] = []
    confirmed_timeframes: list[str] = []

    for timeframe, reading, max_rsi in per_timeframe:
        rsi_ok = reading.rsi is not None and reading.rsi < max_rsi
        timeframe_matches = [
            divergence_signal_detail(sig, timeframe) for sig in reading.divergences if sig.kind == "bearish"
        ]
        confirmed = rsi_ok and len(timeframe_matches) > 0
        conditions[f"{timeframe}_rsi_below_max"] = rsi_ok
        conditions[f"{timeframe}_bearish_divergence"] = len(timeframe_matches) > 0
        conditions[f"{timeframe}_confirmed"] = confirmed
        if confirmed:
            confirmed_timeframes.append(timeframe.upper())
            matches.extend(timeframe_matches)

    qualifies = len(confirmed_timeframes) > 0

    if qualifies:
        best = matches[0]
        explanation = (
            f"NRD confirmed on {' + '.join(confirmed_timeframes)}: price moved {best['price_change_pct']:+.2f}% "
            f"between swing highs while RSI moved {best['rsi_change']:+.1f} the opposite way "
            f"(RSI {best['rsi1']:.1f} -> {best['rsi2']:.1f}) on {best['timeframe']}, with that timeframe's own "
            f"RSI below its ceiling — a downtrend context consistent with a bearish reversal setup."
        )
    else:
        explanation = "NRD not confirmed: no timeframe (daily/weekly/monthly) had both a bearish divergence and a passing RSI ceiling."

    return StrategySignal(
        strategy="NRD",
        symbol=result.symbol,
        sector=result.sector,
        qualifies=qualifies,
        signal_date=result.data_as_of,
        daily_rsi=d,
        weekly_rsi=w,
        monthly_rsi=m,
        conditions=conditions,
        explanation=explanation,
        extra={"divergences": matches, "divergence_timeframes": confirmed_timeframes},
    )
