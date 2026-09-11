from __future__ import annotations

from backend.config.multi_strategy_config import PRDConfig
from backend.screeners.stock_analysis import StockAnalysisResult
from backend.strategies.types import StrategySignal, divergence_signal_detail


def evaluate_prd(result: StockAnalysisResult, config: PRDConfig) -> StrategySignal:
    """
    PRD (Positive Reverse Divergence) = a genuine bullish RSI divergence
    (price makes a lower low while RSI makes a higher low — real swing
    points, see backend/divergence/detector.py), evaluated INDEPENDENTLY on
    each of daily/weekly/monthly. A timeframe confirms PRD only when BOTH
    a bullish divergence exists on that timeframe AND that same timeframe's
    own RSI is above its floor (an uptrend context) — the divergence
    timeframe and the RSI timeframe are never cross-coupled, so a missing
    or failing RSI on one timeframe can never block a different timeframe
    that already confirms on its own. The stock qualifies for PRD if ANY
    ONE (or more) of the three timeframes confirms — not all three at once.
    """
    d, w, m = result.daily.rsi, result.weekly.rsi, result.monthly.rsi

    per_timeframe = (
        ("daily", result.daily, config.daily_min),
        ("weekly", result.weekly, config.weekly_min),
        ("monthly", result.monthly, config.monthly_min),
    )

    conditions: dict[str, bool] = {}
    matches: list[dict] = []
    confirmed_timeframes: list[str] = []

    for timeframe, reading, min_rsi in per_timeframe:
        rsi_ok = reading.rsi is not None and reading.rsi > min_rsi
        timeframe_matches = [
            divergence_signal_detail(sig, timeframe) for sig in reading.divergences if sig.kind == "bullish"
        ]
        confirmed = rsi_ok and len(timeframe_matches) > 0
        conditions[f"{timeframe}_rsi_above_min"] = rsi_ok
        conditions[f"{timeframe}_bullish_divergence"] = len(timeframe_matches) > 0
        conditions[f"{timeframe}_confirmed"] = confirmed
        if confirmed:
            confirmed_timeframes.append(timeframe.upper())
            matches.extend(timeframe_matches)

    qualifies = len(confirmed_timeframes) > 0

    if qualifies:
        best = matches[0]
        explanation = (
            f"PRD confirmed on {' + '.join(confirmed_timeframes)}: price moved {best['price_change_pct']:+.2f}% "
            f"between swing lows while RSI moved {best['rsi_change']:+.1f} the opposite way "
            f"(RSI {best['rsi1']:.1f} -> {best['rsi2']:.1f}) on {best['timeframe']}, with that timeframe's own "
            f"RSI above its floor — an uptrend context consistent with a bullish reversal setup."
        )
    else:
        explanation = "PRD not confirmed: no timeframe (daily/weekly/monthly) had both a bullish divergence and a passing RSI floor."

    return StrategySignal(
        strategy="PRD",
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
