from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from backend.config.sector_mapping import resolve_sector_index
from backend.config.strategy_config import SectorRSIConfig
from backend.indicators.resample import to_monthly, to_weekly
from backend.indicators.rsi import rsi


@dataclass
class TimeframeStats:
    return_pct: float | None
    rsi: float | None


@dataclass
class BenchmarkStats:
    daily: TimeframeStats
    weekly: TimeframeStats
    monthly: TimeframeStats


@dataclass
class SectorAnalysis:
    tapetide_sector: str
    nse_index: str | None
    available: bool
    unavailable_reason: str | None
    daily: TimeframeStats | None = None
    weekly: TimeframeStats | None = None
    monthly: TimeframeStats | None = None
    daily_vs_nifty: float | None = None
    weekly_vs_nifty: float | None = None
    monthly_vs_nifty: float | None = None
    meets_rsi_thresholds: bool = False
    outperforms_nifty: bool = False
    sector_score: float = 0.0
    outperformance_component: float = 0.0  # 0-100, matches ScoringWeights.sector_outperformance
    rsi_component: float = 0.0  # 0-100, matches ScoringWeights.sector_rsi
    # Tapetide's get_index_history has no pagination, and silently TRUNCATES
    # large responses by dropping the most recent bars while keeping old ones
    # (confirmed: a "6m" request for a big sector comes back claiming 127
    # bars/current-to-date in its metadata, but the actual bars array stops
    # ~6 weeks early) — so any Tapetide window wide enough for weekly/monthly
    # RSI is at serious risk of being silently stale. When an Angel-One-
    # sourced longer series is supplied (see
    # backend/config/sector_angelone_mapping.py) and covers enough history,
    # weekly/monthly stats are computed entirely from THAT series (never
    # blended bar-by-bar with Tapetide's) and the source is set to
    # "ANGEL_ONE". If no mapping exists for this sector, or Angel One's own
    # data is also too short, this is "UNAVAILABLE" and that timeframe is
    # genuinely not enforced rather than computed from stale data.
    weekly_data_source: str = "UNAVAILABLE"
    monthly_data_source: str = "UNAVAILABLE"


def _last_completed_return_pct(close: pd.Series) -> float | None:
    if len(close) < 2:
        return None
    return float((close.iloc[-1] / close.iloc[-2] - 1.0) * 100.0)


def _rsi_last(series: pd.Series) -> float | None:
    r = rsi(series, period=14)
    if len(r) == 0 or pd.isna(r.iloc[-1]):
        return None
    return float(r.iloc[-1])


def _monthly_stats_from(ohlc: pd.DataFrame | None) -> TimeframeStats:
    if ohlc is None or ohlc.empty:
        return TimeframeStats(None, None)
    monthly = to_monthly(ohlc)["close"]
    return TimeframeStats(_last_completed_return_pct(monthly), _rsi_last(monthly))


def _weekly_stats_from(ohlc: pd.DataFrame | None) -> TimeframeStats:
    if ohlc is None or ohlc.empty:
        return TimeframeStats(None, None)
    weekly = to_weekly(ohlc)["close"]
    return TimeframeStats(_last_completed_return_pct(weekly), _rsi_last(weekly))


def compute_benchmark_stats(nifty_ohlc: pd.DataFrame, nifty_angelone_override: pd.DataFrame | None = None) -> BenchmarkStats:
    close = nifty_ohlc["close"]

    weekly_stats = _weekly_stats_from(nifty_angelone_override)
    if weekly_stats.rsi is None:
        weekly_stats = _weekly_stats_from(nifty_ohlc)

    monthly_stats = _monthly_stats_from(nifty_angelone_override)
    if monthly_stats.rsi is None:
        monthly_stats = _monthly_stats_from(nifty_ohlc)

    return BenchmarkStats(
        daily=TimeframeStats(_last_completed_return_pct(close), _rsi_last(close)),
        weekly=weekly_stats,
        monthly=monthly_stats,
    )


def analyze_sector(
    tapetide_sector: str,
    sector_ohlc: pd.DataFrame | None,
    benchmark: BenchmarkStats,
    config: SectorRSIConfig,
    angelone_ohlc_override: pd.DataFrame | None = None,
    tradingview_weekly_rsi: float | None = None,
    tradingview_monthly_rsi: float | None = None,
) -> SectorAnalysis:
    """
    tradingview_weekly_rsi / tradingview_monthly_rsi: an OPTIONAL, LAST-RESORT
    fallback — the RSI value from the most recent TradingView SECTOR_RSI
    webhook signal for this sector's NSE index (see
    backend/services/tradingview_service.get_latest_sector_rsi), used only
    when neither Angel One's override series nor Tapetide's own window could
    produce that timeframe's RSI. Carries no return_pct (TradingView sends
    RSI only), so weekly_vs_nifty/monthly_vs_nifty stay None for a
    TradingView-sourced timeframe exactly as they already do for any other
    "unavailable" timeframe — outperforms_nifty and meets_rsi_thresholds
    degrade the same honest way as the existing UNAVAILABLE path, never a
    stock-sector-metadata substitute (spec section 11).
    """
    nse_index = resolve_sector_index(tapetide_sector)

    if nse_index is None:
        return SectorAnalysis(
            tapetide_sector=tapetide_sector,
            nse_index=None,
            available=False,
            unavailable_reason=f"No NSE sectoral index mapped for '{tapetide_sector}' — DATA UNAVAILABLE.",
        )

    if sector_ohlc is None or sector_ohlc.empty:
        return SectorAnalysis(
            tapetide_sector=tapetide_sector,
            nse_index=nse_index,
            available=False,
            unavailable_reason=f"No index history returned for '{nse_index}' — DATA UNAVAILABLE.",
        )

    close = sector_ohlc["close"]

    daily_stats = TimeframeStats(_last_completed_return_pct(close), _rsi_last(close))

    have_override = angelone_ohlc_override is not None and not angelone_ohlc_override.empty

    weekly_data_source = "UNAVAILABLE"
    weekly_stats = TimeframeStats(None, None)
    if have_override:
        candidate = _weekly_stats_from(angelone_ohlc_override)
        if candidate.rsi is not None:
            weekly_stats = candidate
            weekly_data_source = "ANGEL_ONE"
    if weekly_stats.rsi is None:
        # Fall back to Tapetide's own window. Note this is only trustworthy
        # for sectors whose Tapetide history is naturally short enough to
        # avoid the truncation bug above (e.g. recently-added indices) —
        # computed honestly either way, and "UNAVAILABLE" if it yields NaN.
        candidate = _weekly_stats_from(sector_ohlc)
        if candidate.rsi is not None:
            weekly_stats = candidate
            weekly_data_source = "TAPETIDE"
    if weekly_stats.rsi is None and tradingview_weekly_rsi is not None:
        weekly_stats = TimeframeStats(None, tradingview_weekly_rsi)
        weekly_data_source = "TRADINGVIEW"

    monthly_data_source = "UNAVAILABLE"
    monthly_stats = TimeframeStats(None, None)
    if have_override:
        candidate = _monthly_stats_from(angelone_ohlc_override)
        if candidate.rsi is not None:
            monthly_stats = candidate
            monthly_data_source = "ANGEL_ONE"
    if monthly_stats.rsi is None:
        # Fall back to Tapetide's own (short) window — usually still None
        # given the ~6-month cap, but computed honestly either way.
        candidate = _monthly_stats_from(sector_ohlc)
        if candidate.rsi is not None:
            monthly_stats = candidate
            monthly_data_source = "TAPETIDE"
    if monthly_stats.rsi is None and tradingview_monthly_rsi is not None:
        monthly_stats = TimeframeStats(None, tradingview_monthly_rsi)
        monthly_data_source = "TRADINGVIEW"

    daily_vs_nifty = (
        daily_stats.return_pct - benchmark.daily.return_pct
        if daily_stats.return_pct is not None and benchmark.daily.return_pct is not None
        else None
    )
    weekly_vs_nifty = (
        weekly_stats.return_pct - benchmark.weekly.return_pct
        if weekly_stats.return_pct is not None and benchmark.weekly.return_pct is not None
        else None
    )
    monthly_vs_nifty = (
        monthly_stats.return_pct - benchmark.monthly.return_pct
        if monthly_stats.return_pct is not None and benchmark.monthly.return_pct is not None
        else None
    )

    # Outperformance requires every timeframe that's ACTUALLY AVAILABLE to be
    # positive — never fewer than 2 confirmed timeframes (spec: never decide
    # from a single day), but a genuinely unavailable monthly figure doesn't
    # block qualification the way a bad/negative one would.
    available_rs = [v for v in (daily_vs_nifty, weekly_vs_nifty, monthly_vs_nifty) if v is not None]
    outperforms_nifty = len(available_rs) >= 2 and all(v > 0 for v in available_rs)

    # RSI threshold rule: daily is always mandatory. Weekly/monthly are each
    # enforced only when actually computable (never from stale/truncated
    # data — see SectorAnalysis docstring), but at least one of them must be
    # confirmed and passing — daily alone is single-day noise, never enough.
    weekly_ok = weekly_stats.rsi is None or weekly_stats.rsi > config.weekly_min
    monthly_ok = monthly_stats.rsi is None or monthly_stats.rsi > config.monthly_min
    has_confirmation = weekly_stats.rsi is not None or monthly_stats.rsi is not None

    # Alternate path: weekly AND monthly both confirmed and already above
    # their own mins is itself a strong-trend confirmation, so a daily
    # reading that's merely above the lower daily_min_relaxed bar (instead
    # of the full daily_min) still counts — a single lagging daily candle
    # shouldn't override two higher timeframes already confirming strength.
    higher_timeframes_confirmed_strong = (
        weekly_stats.rsi is not None and weekly_stats.rsi > config.weekly_min
        and monthly_stats.rsi is not None and monthly_stats.rsi > config.monthly_min
    )
    daily_threshold = config.daily_min_relaxed if higher_timeframes_confirmed_strong else config.daily_min
    daily_ok = daily_stats.rsi is not None and daily_stats.rsi > daily_threshold

    meets_rsi = daily_ok and weekly_ok and monthly_ok and has_confirmation

    # Sector Outperformance Score (0-100): average of the AVAILABLE relative-
    # strength deltas, scaled and clipped.
    rs_values = available_rs
    outperf_component = max(0.0, min(100.0, 50.0 + (sum(rs_values) / len(rs_values)) * 10.0)) if rs_values else 0.0

    rsi_values = [v for v in (daily_stats.rsi, weekly_stats.rsi, monthly_stats.rsi) if v is not None]
    rsi_component = sum(rsi_values) / len(rsi_values) if rsi_values else 0.0

    sector_score = 0.5 * outperf_component + 0.5 * rsi_component

    return SectorAnalysis(
        tapetide_sector=tapetide_sector,
        nse_index=nse_index,
        available=True,
        unavailable_reason=None,
        daily=daily_stats,
        weekly=weekly_stats,
        monthly=monthly_stats,
        daily_vs_nifty=daily_vs_nifty,
        weekly_vs_nifty=weekly_vs_nifty,
        monthly_vs_nifty=monthly_vs_nifty,
        meets_rsi_thresholds=meets_rsi,
        outperforms_nifty=outperforms_nifty,
        sector_score=sector_score,
        outperformance_component=outperf_component,
        rsi_component=rsi_component,
        weekly_data_source=weekly_data_source,
        monthly_data_source=monthly_data_source,
    )
