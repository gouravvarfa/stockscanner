from __future__ import annotations

import asyncio
import datetime as dt
import logging
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from backend.config.data_source_config import DataSourceMode
from backend.config.multi_strategy_config import DEFAULT_MULTI_STRATEGY_CONFIG, MultiStrategyConfig
from backend.config.sector_angelone_mapping import NIFTY_50_ANGELONE_NAME, resolve_angelone_index_name
from backend.config.sector_mapping import resolve_sector_index
from backend.config.strategy_config import StrategyConfig
from backend.providers import call_metrics
from backend.providers.angelone_provider import AngelOneProvider
from backend.providers.base import MarketDataProvider
from backend.providers.market_data_router import MarketDataRouter
from backend.screeners.stock_analysis import StockAnalysisResult, analyze_stock
from backend.sector_analysis.engine import SectorAnalysis, analyze_sector, compute_benchmark_stats
from backend.strategies.runner import evaluate_all_strategies
from backend.strategies.types import StrategySignal
from backend.strategies.value_buy import evaluate_value_buy

# Enough calendar days to reliably get 15+ MONTHLY (and comfortably more
# than enough WEEKLY) closes after resampling — Tapetide's get_index_history
# cannot supply this itself: it has no pagination, and silently truncates
# any large response by dropping the most recent bars while keeping old
# ones (confirmed: a "6m"/127-bar request for a big sector actually returns
# only ~98 bars ending ~6 weeks early). So both weekly and monthly stats for
# the sectors Angel One's index catalog covers are sourced from this longer,
# untruncated Angel One series instead.
ANGELONE_OHLC_LOOKBACK_DAYS = 600
# Tapetide's own daily-history call is now used ONLY for the DAILY figure —
# "3m" reliably fits under Tapetide's response-size cap without truncation
# (verified: current-day data, no dropped tail), unlike "6m"/"1y"/"max".
TAPETIDE_DAILY_INTERVAL = "3m"


async def _fetch_angelone_index_ohlc_source(
    angelone_provider: AngelOneProvider | None, angel_index_name: str | None, label: str, errors: list[str]
) -> pd.DataFrame | None:
    if angelone_provider is None or angel_index_name is None:
        return None
    try:
        match = await angelone_provider.resolve_index(angel_index_name)
        if match is None:
            return None
        return await angelone_provider.get_intraday_ohlc(match.exch_seg, match.token, "ONE_DAY", ANGELONE_OHLC_LOOKBACK_DAYS)
    except Exception as exc:  # noqa: BLE001 — this is a best-effort supplement, never fatal
        logger.warning("Angel One OHLC-source fetch failed for %s (%s): %s", label, angel_index_name, exc)
        errors.append(f"Angel One weekly/monthly data unavailable for {label}: {exc}")
        return None

logger = logging.getLogger("scanner.scan_service")


@dataclass
class ScanOutcome:
    started_at: dt.datetime
    finished_at: dt.datetime
    execution_seconds: float
    universe_requested: int
    universe_returned: int
    universe_complete: bool
    universe_note: str | None
    stocks_scanned: int
    stocks_failed: int
    failed_symbols: list[str]
    sector_analyses: dict[str, SectorAnalysis]
    qualifying_sectors: list[str]
    all_results: list[StockAnalysisResult]
    qualifying_results: list[StockAnalysisResult]
    top10: list[StockAnalysisResult]
    top3: list[StockAnalysisResult]
    best: StockAnalysisResult | None
    # Additive: all six strategies (incl. Strategy One) per candidate, keyed by
    # strategy name -> list of StrategySignal. A stock qualifying for several
    # strategies appears once per strategy list, never deduplicated.
    strategy_signals: dict[str, list[StrategySignal]] = field(default_factory=dict)
    # Additive: per-stock daily candles are fetched through the capability-based
    # market-data router (Tapetide preferred, Angel One as fallback — see
    # backend/providers/market_data_router.py). This summarizes which provider
    # actually served each stock, so the scan never silently hides a fallback.
    data_source_mode: str = "auto"
    data_source_summary: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


async def run_full_scan(
    provider: MarketDataProvider,
    config: StrategyConfig,
    stock_history_days: int = 800,
    # Kept modest since per-stock daily fetches now funnel through Angel One
    # first in AUTO mode (see _fetch_ohlcv below) — its historical-candle
    # endpoint enforces a strict per-second rate limit (see the Expiry Level 1
    # pacing fix), so a large burst of concurrent requests risks the same
    # intermittent "HTTP 403 non-JSON response" throttling seen there.
    max_concurrent_stock_calls: int = 4,
    multi_strategy_config: MultiStrategyConfig | None = None,
    market_data_router: MarketDataRouter | None = None,
    data_source_mode: DataSourceMode = "auto",
    angelone_provider: AngelOneProvider | None = None,
) -> ScanOutcome:
    multi_strategy_config = multi_strategy_config or DEFAULT_MULTI_STRATEGY_CONFIG
    started_at = dt.datetime.utcnow()
    errors: list[str] = []

    if data_source_mode == "angel_one":
        # Universe/sector data (NIFTY 200 constituents, sectoral index returns)
        # has no Angel One equivalent in this project (see capabilities.py) —
        # explicit Angel One mode must say so clearly, not silently fall
        # through to Tapetide anyway (spec: explicit mode never substitutes
        # another provider).
        raise RuntimeError(
            "Angel One selected as the data source, but the NIFTY 200 universe and sector data required for "
            "Strategy One/GFS/Advanced GFS/PRD/NRD/Value Buy is only available from Tapetide in this project "
            "— Angel One has no equivalent NIFTY 200/sector capability. Switch to Auto or Tapetide mode, or "
            "use Expiry Level 1/5 which are Angel-One-native."
        )

    universe = await provider.get_universe("nifty-200")
    stocks = universe["stocks"]
    logger.info("Universe: %s/%s (complete=%s)", universe["returned"], universe["requested"], universe["complete"])

    # Angel One's 600-day series (already fetched below for weekly/monthly)
    # already contains today's daily bars too — reusing it for the DAILY
    # figure as well (instead of ALSO making a separate Tapetide "3m" call)
    # cuts one Tapetide call per Angel-One-covered index, with no loss of
    # freshness (it's actually MORE current than Tapetide's own truncation-
    # prone history — see ANGELONE_OHLC_LOOKBACK_DAYS above). Tapetide is
    # only called when Angel One has no coverage or its fetch failed.
    nifty_angelone_override = await _fetch_angelone_index_ohlc_source(
        angelone_provider, NIFTY_50_ANGELONE_NAME, "NIFTY 50 benchmark", errors
    )
    if nifty_angelone_override is not None and not nifty_angelone_override.empty:
        nifty_ohlc = nifty_angelone_override
    else:
        nifty_ohlc = await provider.get_index_ohlc("Nifty 50", TAPETIDE_DAILY_INTERVAL)
        if nifty_ohlc.empty:
            raise RuntimeError("NIFTY 50 benchmark data unavailable from Tapetide — cannot proceed with scan.")
    benchmark = compute_benchmark_stats(nifty_ohlc, nifty_angelone_override)

    sectors_present = sorted({s["sector"] for s in stocks if s.get("sector")})
    sector_analyses: dict[str, SectorAnalysis] = {}
    for sector in sectors_present:
        nse_index = resolve_sector_index(sector)
        sector_ohlc = None
        angelone_override = None
        if nse_index:
            angel_index_name = resolve_angelone_index_name(nse_index)
            angelone_override = await _fetch_angelone_index_ohlc_source(
                angelone_provider, angel_index_name, f"sector '{sector}'", errors
            )
            if angelone_override is not None and not angelone_override.empty:
                sector_ohlc = angelone_override
            else:
                try:
                    sector_ohlc = await provider.get_index_ohlc(nse_index, TAPETIDE_DAILY_INTERVAL)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"Sector index fetch failed for '{nse_index}': {exc}")
                    logger.warning("Sector index fetch failed for %s: %s", nse_index, exc)
        sector_analyses[sector] = analyze_sector(sector, sector_ohlc, benchmark, config.sector_rsi, angelone_override)

    qualifying_sectors = [
        sector
        for sector, analysis in sector_analyses.items()
        if analysis.available and analysis.meets_rsi_thresholds and analysis.outperforms_nifty
    ]
    logger.info("Qualifying sectors: %s", qualifying_sectors)

    candidates = [s for s in stocks if s.get("sector") in qualifying_sectors]
    # Value Buy does not depend on sector strength at all internally (see
    # backend/strategies/value_buy.py — it only checks the stock's own
    # monthly RSI support zone, weekly candle, and daily trigger), and the
    # user explicitly wants Value Buy candidates regardless of whether their
    # sector currently qualifies. So it additionally runs over every stock
    # NOT already covered by the sector-qualified candidates above — the
    # other five strategies are untouched and still only ever see
    # sector-qualified stocks, exactly as before.
    candidate_symbols = {s["symbol"] for s in candidates}
    value_buy_only_candidates = [s for s in stocks if s["symbol"] not in candidate_symbols]

    semaphore = asyncio.Semaphore(max_concurrent_stock_calls)
    all_results: list[StockAnalysisResult] = []
    failed_symbols: list[str] = []
    strategy_signals: dict[str, list[StrategySignal]] = {name: [] for name in
        ["Strategy One", "GFS", "Advanced GFS", "PRD", "NRD", "Value Buy"]}
    data_source_summary: dict[str, int] = {}

    async def _fetch_ohlcv(symbol: str) -> tuple[pd.DataFrame, str]:
        if market_data_router is None:
            return await provider.get_stock_ohlcv(symbol, days=stock_history_days), "tapetide"

        if data_source_mode == "auto":
            # Per-stock daily OHLCV is equally available from either provider,
            # so in AUTO mode prefer Angel One FIRST here — Tapetide's 50/day
            # free-tier quota is the scarce resource (already spent on
            # universe/sector data above), while Angel One has no such daily
            # cap. Tapetide remains the safety-net fallback if Angel One
            # itself fails for this symbol, so a scan never loses a stock
            # just because Angel One had a bad moment. An explicit "tapetide"
            # or "angel_one" mode selection is never overridden — this only
            # applies to AUTO.
            try:
                routed = await market_data_router.get_candles(
                    symbol, "daily", stock_history_days, "angel_one", strategy_name="Strategy One+GFS+..."
                )
            except Exception:  # noqa: BLE001
                call_metrics.record_fallback()
                routed = await market_data_router.get_candles(
                    symbol, "daily", stock_history_days, "tapetide", strategy_name="Strategy One+GFS+..."
                )
        else:
            routed = await market_data_router.get_candles(
                symbol, "daily", stock_history_days, data_source_mode, strategy_name="Strategy One+GFS+..."
            )
        data_source_summary[routed.data_source] = data_source_summary.get(routed.data_source, 0) + 1
        return routed.data, routed.data_source

    async def process(stock_meta: dict[str, Any]) -> None:
        symbol = stock_meta["symbol"]
        async with semaphore:
            try:
                ohlcv, stock_data_source = await _fetch_ohlcv(symbol)
                result = analyze_stock(
                    symbol, stock_meta.get("sector", "Unknown"), ohlcv,
                    sector_analyses.get(stock_meta.get("sector")), config,
                )
                if result is not None:
                    all_results.append(result)
                    # Same already-fetched OHLCV and already-computed indicators
                    # feed every strategy — no extra Tapetide calls per strategy.
                    signals = evaluate_all_strategies(result, ohlcv, multi_strategy_config)
                    for name, signal in signals.items():
                        if signal.qualifies:
                            # Dashboard-facing metadata only — never consulted by any
                            # strategy's own qualification logic.
                            signal.extra["current_price"] = result.current_price
                            signal.extra["data_source"] = stock_data_source
                            strategy_signals[name].append(signal)
                else:
                    failed_symbols.append(symbol)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Stock %s failed: %s", symbol, exc)
                failed_symbols.append(symbol)
                errors.append(f"{symbol}: {exc}")

    async def process_value_buy_only(stock_meta: dict[str, Any]) -> None:
        symbol = stock_meta["symbol"]
        async with semaphore:
            try:
                ohlcv, stock_data_source = await _fetch_ohlcv(symbol)
                result = analyze_stock(
                    symbol, stock_meta.get("sector", "Unknown"), ohlcv,
                    sector_analyses.get(stock_meta.get("sector")), config,
                )
                if result is not None:
                    signal = evaluate_value_buy(result, ohlcv, multi_strategy_config.value_buy)
                    if signal.qualifies:
                        signal.extra["current_price"] = result.current_price
                        signal.extra["data_source"] = stock_data_source
                        strategy_signals["Value Buy"].append(signal)
                else:
                    failed_symbols.append(symbol)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Stock %s failed (Value Buy only): %s", symbol, exc)
                failed_symbols.append(symbol)
                errors.append(f"{symbol}: {exc}")

    await asyncio.gather(
        *(process(s) for s in candidates),
        *(process_value_buy_only(s) for s in value_buy_only_candidates),
    )

    qualifying_results = [
        r for r in all_results
        if r.meets_weekly_rsi_band and r.meets_monthly_rsi_min and not r.disqualified_by_divergence
    ]
    qualifying_results.sort(key=lambda r: r.score.total_score, reverse=True)

    top10 = qualifying_results[:10]
    top3 = qualifying_results[:3]
    best = qualifying_results[0] if qualifying_results else None

    finished_at = dt.datetime.utcnow()

    return ScanOutcome(
        started_at=started_at,
        finished_at=finished_at,
        execution_seconds=(finished_at - started_at).total_seconds(),
        universe_requested=universe["requested"],
        universe_returned=universe["returned"],
        universe_complete=universe["complete"],
        universe_note=universe.get("note"),
        stocks_scanned=len(candidates) + len(value_buy_only_candidates),
        stocks_failed=len(failed_symbols),
        failed_symbols=failed_symbols,
        sector_analyses=sector_analyses,
        qualifying_sectors=qualifying_sectors,
        all_results=all_results,
        qualifying_results=qualifying_results,
        top10=top10,
        top3=top3,
        best=best,
        strategy_signals=strategy_signals,
        data_source_mode=data_source_mode,
        data_source_summary=data_source_summary,
        errors=errors,
    )
