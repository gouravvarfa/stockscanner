from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from backend.config.strategy_config import StrategyConfig
from backend.divergence.detector import DivergenceSignal, detect_divergences, has_significant_bearish_divergence
from backend.fibonacci.engine import FibonacciAnalysis, calculate_fibonacci, has_bullish_confirmation
from backend.indicators.adx import adx
from backend.indicators.macd import macd
from backend.indicators.moving_averages import ema
from backend.indicators.resample import to_monthly, to_weekly
from backend.indicators.rsi import rsi
from backend.indicators.volume import distance_from_52w_high, volume_ratio
from backend.ranking.scorer import ScoreBreakdown, compute_score


@dataclass
class TimeframeReading:
    # 2026-09-26 (master RSI-freshness change): `rsi` is now the LATEST/LIVE
    # value — for weekly/monthly this includes the current still-forming
    # period (see analyze_stock's live_weekly_df/live_monthly_df), matching
    # what the chart itself shows for the same stock/timeframe (same
    # to_weekly/to_monthly(include_partial=True) + same Wilder RSI(14)).
    # `previous_rsi` is the prior CONFIRMED value (completed periods only) —
    # kept for reference/API exposure, never used for qualification.
    rsi: float | None
    divergences: list[DivergenceSignal]
    has_bearish_divergence: bool
    # Index of the latest bar in the CONFIRMED series this reading's
    # divergence structure was computed from (i.e. len(close) - 1) — used by
    # PRD/NRD to measure how many bars ago a divergence's confirming pivot
    # occurred (freshness), independent of any absolute date. Divergence
    # structure/A-B pivots are deliberately computed from confirmed
    # (non-live) data only — see module docstring note in analyze_stock.
    last_bar_index: int = 0
    previous_rsi: float | None = None


@dataclass
class StockAnalysisResult:
    symbol: str
    current_price: float
    data_as_of: pd.Timestamp
    daily: TimeframeReading
    weekly: TimeframeReading
    monthly: TimeframeReading
    fibonacci: FibonacciAnalysis | None
    ema20: float | None
    ema50: float | None
    ema200: float | None
    macd_histogram: float | None
    adx_value: float | None
    volume_ratio_value: float | None
    distance_from_52w_high_pct: float | None
    meets_weekly_rsi_band: bool
    meets_monthly_rsi_min: bool
    disqualified_by_divergence: bool
    score: ScoreBreakdown
    data_warnings: list[str] = field(default_factory=list)


def _timeframe_reading(
    close: pd.Series, high: pd.Series, low: pd.Series, config: StrategyConfig,
    live_close: pd.Series | None = None,
) -> TimeframeReading:
    """
    `close`/`high`/`low` are the CONFIRMED (completed-periods-only) series —
    divergence/pivot structure is always computed from these, unchanged.
    `live_close`, when given, is the SAME timeframe's close series but
    including the current still-forming period (e.g.
    to_monthly(daily_ohlcv, include_partial=True)) — used ONLY to compute
    the latest/live RSI value now exposed as `.rsi` (2026-09-26). Never
    fed into divergence detection, so PRD/NRD structural confirmation and
    A/B pivot RSI values are completely unaffected by this.
    """
    r = rsi(close, period=14)
    signals = detect_divergences(high, low, close, r, config.divergence)
    bearish = has_significant_bearish_divergence(signals)
    confirmed_rsi = float(r.iloc[-1]) if len(r) and not pd.isna(r.iloc[-1]) else None
    latest_rsi = confirmed_rsi
    if live_close is not None and len(live_close) >= len(close):
        live_r = rsi(live_close, period=14)
        if len(live_r) and not pd.isna(live_r.iloc[-1]):
            latest_rsi = float(live_r.iloc[-1])
    return TimeframeReading(
        rsi=latest_rsi,
        previous_rsi=confirmed_rsi,
        divergences=signals,
        has_bearish_divergence=bearish,
        last_bar_index=len(close) - 1,
    )


def _rsi_component(weekly_rsi: float | None, monthly_rsi: float | None, cfg) -> float:
    weekly_score = 0.0
    if weekly_rsi is not None:
        if cfg.weekly_min <= weekly_rsi <= cfg.weekly_max:
            weekly_score = 100.0
        else:
            distance = min(abs(weekly_rsi - cfg.weekly_min), abs(weekly_rsi - cfg.weekly_max))
            weekly_score = max(0.0, 100.0 - distance * 8.0)

    monthly_score = 0.0
    if monthly_rsi is not None:
        if monthly_rsi >= cfg.monthly_min:
            monthly_score = 100.0
        else:
            monthly_score = max(0.0, 100.0 - (cfg.monthly_min - monthly_rsi) * 5.0)

    return 0.5 * weekly_score + 0.5 * monthly_score


def _divergence_component(daily: TimeframeReading, weekly: TimeframeReading, monthly: TimeframeReading) -> float:
    score = 100.0
    if daily.has_bearish_divergence:
        score -= 35.0
    if weekly.has_bearish_divergence:
        score -= 35.0
    if monthly.has_bearish_divergence:
        score -= 30.0
    return max(0.0, score)


def _fibonacci_component(analysis: FibonacciAnalysis | None, bullish_confirmed: bool) -> float:
    if analysis is None:
        return 0.0
    if analysis.in_preferred_zone and bullish_confirmed:
        return 100.0
    if analysis.in_preferred_zone:
        return 70.0
    # Scale down by distance from the nearest level, capped.
    return max(0.0, 50.0 - abs(analysis.nearest_level.distance_pct) * 3.0)


def _trend_component(price: float, ema20: float | None, ema50: float | None, ema200: float | None) -> float:
    checks = [
        ema20 is not None and price > ema20,
        ema50 is not None and price > ema50,
        ema200 is not None and price > ema200,
    ]
    return sum(checks) / len(checks) * 100.0


def _volume_component(ratio: float | None, min_ratio: float) -> float:
    if ratio is None:
        return 0.0
    if ratio >= min_ratio:
        return min(100.0, 60.0 + (ratio - min_ratio) * 40.0)
    return max(0.0, ratio / min_ratio * 60.0)


def _macd_adx_component(macd_hist: float | None, adx_value: float | None, adx_healthy_min: float) -> float:
    macd_ok = macd_hist is not None and macd_hist > 0
    adx_ok = adx_value is not None and adx_value >= adx_healthy_min
    if macd_ok and adx_ok:
        return 100.0
    if macd_ok or adx_ok:
        return 55.0
    return 20.0


def analyze_stock(
    symbol: str,
    daily_ohlcv: pd.DataFrame,
    config: StrategyConfig,
) -> StockAnalysisResult | None:
    warnings: list[str] = []
    if daily_ohlcv is None or daily_ohlcv.empty or len(daily_ohlcv) < 60:
        return None

    close, high, low = daily_ohlcv["close"], daily_ohlcv["high"], daily_ohlcv["low"]
    weekly_df = to_weekly(daily_ohlcv)
    monthly_df = to_monthly(daily_ohlcv)
    # Live/latest RSI inputs (2026-09-26): the SAME resample, just keeping
    # the current still-forming week/month instead of dropping it — same
    # to_weekly/to_monthly this file already used, same include_partial
    # flag the chart/Value Buy already rely on. Daily has no separate live
    # variant here: `daily_ohlcv` is already "the latest available daily
    # data" (Angel One's own daily fetch only ever returns completed days —
    # a true intraday-forming daily candle is the live tick engine's
    # concern, backend/live/candle_builder.py, not this batch-scan path).
    live_weekly_df = to_weekly(daily_ohlcv, include_partial=True)
    live_monthly_df = to_monthly(daily_ohlcv, include_partial=True)

    daily_reading = _timeframe_reading(close, high, low, config)
    weekly_reading = (
        _timeframe_reading(
            weekly_df["close"], weekly_df["high"], weekly_df["low"], config,
            live_close=live_weekly_df["close"],
        )
        if len(weekly_df) >= 20
        else TimeframeReading(None, [], False)
    )
    monthly_reading = (
        _timeframe_reading(
            monthly_df["close"], monthly_df["high"], monthly_df["low"], config,
            live_close=live_monthly_df["close"],
        )
        if len(monthly_df) >= 20
        else TimeframeReading(None, [], False)
    )
    if weekly_reading.rsi is None:
        warnings.append("Weekly RSI unavailable (insufficient weekly history) — DATA UNAVAILABLE.")
    if monthly_reading.rsi is None:
        warnings.append("Monthly RSI unavailable (insufficient monthly history) — DATA UNAVAILABLE.")

    fib_analysis = calculate_fibonacci(high, low, close, config.fibonacci)
    bullish_confirmed = (
        has_bullish_confirmation(close, fib_analysis) if fib_analysis is not None else False
    )
    if fib_analysis is None:
        warnings.append("Fibonacci levels unavailable (insufficient swing data) — DATA UNAVAILABLE.")

    ema20 = ema(close, config.trend.ema_fast).iloc[-1]
    ema50 = ema(close, config.trend.ema_medium).iloc[-1]
    ema200_series = ema(close, config.trend.ema_slow)
    ema200 = ema200_series.iloc[-1] if not pd.isna(ema200_series.iloc[-1]) else None
    if ema200 is None:
        warnings.append("200-EMA unavailable (fewer than 200 daily bars) — DATA UNAVAILABLE.")

    macd_df = macd(close)
    macd_hist = float(macd_df["histogram"].iloc[-1]) if not pd.isna(macd_df["histogram"].iloc[-1]) else None

    adx_df = adx(high, low, close, period=config.trend.adx_period)
    adx_value = float(adx_df["adx"].iloc[-1]) if not pd.isna(adx_df["adx"].iloc[-1]) else None

    vol_ratio = volume_ratio(daily_ohlcv["volume"], period=config.trend.volume_avg_period)
    vol_ratio_value = float(vol_ratio.iloc[-1]) if not pd.isna(vol_ratio.iloc[-1]) else None

    dist_52w = distance_from_52w_high(close, high)
    dist_52w_value = float(dist_52w.iloc[-1]) if not pd.isna(dist_52w.iloc[-1]) else None

    meets_weekly_band = (
        weekly_reading.rsi is not None
        and config.stock_rsi.weekly_min <= weekly_reading.rsi <= config.stock_rsi.weekly_max
    )
    meets_monthly_min = monthly_reading.rsi is not None and monthly_reading.rsi >= config.stock_rsi.monthly_min

    disqualified_by_divergence = (
        daily_reading.has_bearish_divergence
        or weekly_reading.has_bearish_divergence
        or monthly_reading.has_bearish_divergence
    ) if config.divergence.strict_mode else weekly_reading.has_bearish_divergence

    components = {
        "stock_rsi": _rsi_component(weekly_reading.rsi, monthly_reading.rsi, config.stock_rsi),
        "divergence": _divergence_component(daily_reading, weekly_reading, monthly_reading),
        "fibonacci": _fibonacci_component(fib_analysis, bullish_confirmed),
        "trend": _trend_component(float(close.iloc[-1]), ema20, ema50, ema200),
        "volume": _volume_component(vol_ratio_value, config.trend.volume_ratio_min),
        "macd_adx": _macd_adx_component(macd_hist, adx_value, config.trend.adx_healthy_min),
    }

    explanation = _build_explanation(components, weekly_reading, monthly_reading, fib_analysis, config)

    score = compute_score(components, config.weights, config.classification, explanation)

    return StockAnalysisResult(
        symbol=symbol,
        current_price=float(close.iloc[-1]),
        data_as_of=close.index[-1],
        daily=daily_reading,
        weekly=weekly_reading,
        monthly=monthly_reading,
        fibonacci=fib_analysis,
        ema20=float(ema20) if not pd.isna(ema20) else None,
        ema50=float(ema50) if not pd.isna(ema50) else None,
        ema200=ema200,
        macd_histogram=macd_hist,
        adx_value=adx_value,
        volume_ratio_value=vol_ratio_value,
        distance_from_52w_high_pct=dist_52w_value,
        meets_weekly_rsi_band=meets_weekly_band,
        meets_monthly_rsi_min=meets_monthly_min,
        disqualified_by_divergence=disqualified_by_divergence,
        score=score,
        data_warnings=warnings,
    )


def _build_explanation(
    components: dict[str, float],
    weekly: TimeframeReading,
    monthly: TimeframeReading,
    fib: FibonacciAnalysis | None,
    config: StrategyConfig,
) -> list[str]:
    lines: list[str] = []

    if weekly.rsi is not None:
        lines.append(
            f"Weekly RSI {weekly.rsi:.1f} "
            f"({'within' if config.stock_rsi.weekly_min <= weekly.rsi <= config.stock_rsi.weekly_max else 'outside'} "
            f"{config.stock_rsi.weekly_min}-{config.stock_rsi.weekly_max} band)."
        )
    if monthly.rsi is not None:
        lines.append(
            f"Monthly RSI {monthly.rsi:.1f} "
            f"({'>=' if monthly.rsi >= config.stock_rsi.monthly_min else '<'} {config.stock_rsi.monthly_min} threshold)."
        )

    if weekly.has_bearish_divergence:
        lines.append("Bearish RSI divergence detected on the weekly timeframe.")
    if monthly.has_bearish_divergence:
        lines.append("Bearish RSI divergence detected on the monthly timeframe.")
    if not weekly.has_bearish_divergence and not monthly.has_bearish_divergence:
        lines.append("No significant bearish RSI divergence detected on weekly/monthly timeframes.")

    if fib is not None:
        lines.append(
            f"Price sits nearest the {fib.nearest_level.ratio:.3f} Fibonacci retracement level "
            f"({fib.nearest_level.distance_pct:+.2f}% away)."
        )

    return lines
