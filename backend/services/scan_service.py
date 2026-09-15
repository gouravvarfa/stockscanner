from __future__ import annotations

import asyncio
import datetime as dt
import logging
from dataclasses import dataclass, field

import pandas as pd

from backend.config.multi_strategy_config import DEFAULT_MULTI_STRATEGY_CONFIG, MultiStrategyConfig
from backend.config.strategy_config import StrategyConfig
from backend.providers.angelone_provider import AngelOneProvider
from backend.providers.market_data_router import fetch_daily_ohlcv
from backend.screeners.stock_analysis import StockAnalysisResult, analyze_stock
from backend.services import universe_loader
from backend.strategies.advanced_gfs import evaluate_advanced_gfs
from backend.strategies.gfs import evaluate_gfs
from backend.strategies.nrd import evaluate_nrd
from backend.strategies.prd import evaluate_prd
from backend.strategies.strategy_one import evaluate_strategy_one
from backend.strategies.types import StrategySignal
from backend.strategies.value_buy import evaluate_value_buy

logger = logging.getLogger("scanner.scan_service")

# Angel One's historical-candle endpoint has no daily-call cap (unlike the
# Tapetide free tier this replaced), so this is generous enough for a
# reliable monthly RSI(14) after weekly/monthly resampling, without being so
# large it wastes bandwidth on data older than needed.
STOCK_HISTORY_DAYS = 800

ALL_SIGNAL_STRATEGY_NAMES = ["Strategy One", "GFS", "Advanced GFS", "PRD", "NRD", "Value Buy"]


@dataclass
class UniverseStockEntry:
    """
    One row of the NIFTY 200 master universe (from NIFTY_200_Sector_List.xlsx)
    — one entry per symbol in that file, independent of whether that stock's
    own price/RSI analysis later succeeded. Built BEFORE any per-stock fetch
    is attempted and then enriched in place as each stock's analysis
    completes — a stock is never removed just because Angel One couldn't
    supply its data.
    """
    symbol: str
    current_price: float | None = None
    daily_rsi: float | None = None
    weekly_rsi: float | None = None
    monthly_rsi: float | None = None
    data_source: str | None = None
    status: str = "PENDING"  # "OK" | "DATA_UNAVAILABLE" | "PENDING" (should never be observed externally)
    status_reason: str | None = None


@dataclass
class ScanOutcome:
    started_at: dt.datetime
    finished_at: dt.datetime
    execution_seconds: float
    universe_requested: int  # NIFTY 200 count (Strategy One/GFS/Advanced GFS/PRD/NRD universe)
    universe_returned: int
    universe_complete: bool
    value_buy_universe_requested: int  # NIFTY 500 count (Value Buy's own, separate universe)
    value_buy_universe_returned: int
    stocks_scanned: int
    stocks_failed: int
    failed_symbols: list[str]
    all_results: list[StockAnalysisResult]
    qualifying_results: list[StockAnalysisResult]
    top10: list[StockAnalysisResult]
    top3: list[StockAnalysisResult]
    best: StockAnalysisResult | None
    # The NIFTY 200 master universe — one entry per symbol in
    # NIFTY_200_Sector_List.xlsx, regardless of whether that stock's own
    # analysis succeeded. Deliberately separate from all_results/
    # qualifying_results/top10/best (Strategy One's own ranking).
    nifty200_universe: list[UniverseStockEntry] = field(default_factory=list)
    # All six strategies' signals, keyed by strategy name. Strategy One/GFS/
    # Advanced GFS/PRD/NRD are evaluated over the NIFTY 200 universe only;
    # Value Buy is evaluated over the separate, larger NIFTY 500 universe.
    strategy_signals: dict[str, list[StrategySignal]] = field(default_factory=dict)
    data_source_summary: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


async def _fetch_and_analyze(
    angelone_provider: AngelOneProvider,
    symbol: str,
    config: StrategyConfig,
    stock_history_days: int,
) -> tuple[StockAnalysisResult | None, pd.DataFrame | None, str | None]:
    """Returns (analysis_result_or_None, daily_ohlcv, error_reason_or_None)."""
    try:
        ohlcv = await fetch_daily_ohlcv(angelone_provider, symbol, stock_history_days)
    except Exception as exc:  # noqa: BLE001 — one bad symbol must never crash the whole scan
        return None, None, str(exc)

    result = analyze_stock(symbol, ohlcv, config)
    if result is None:
        return None, ohlcv, "Insufficient historical data (fewer than 60 daily bars)"
    return result, ohlcv, None


async def run_full_scan(
    angelone_provider: AngelOneProvider,
    config: StrategyConfig,
    stock_history_days: int = STOCK_HISTORY_DAYS,
    # Angel One's historical-candle endpoint enforces a strict per-second
    # rate limit (see the Expiry Level 1 pacing fix) — a large burst of
    # concurrent requests risks intermittent "HTTP 403 non-JSON response"
    # throttling, not a real data problem.
    max_concurrent_stock_calls: int = 4,
    multi_strategy_config: MultiStrategyConfig | None = None,
) -> ScanOutcome:
    multi_strategy_config = multi_strategy_config or DEFAULT_MULTI_STRATEGY_CONFIG
    started_at = dt.datetime.utcnow()
    errors: list[str] = []
    failed_symbols: list[str] = []
    data_source_summary: dict[str, int] = {}

    # Every strategy — Value Buy included — now runs over the single BSE
    # "A Group" universe. Value Buy keeps its own symbol list variable (and
    # its own pass) so the two can diverge again without reshaping the scan,
    # but today they are the same list, so its pass is served entirely from
    # analyzed_cache and costs no extra Angel One calls.
    nifty200_symbols = universe_loader.load_a_group_universe()
    nifty500_symbols = nifty200_symbols
    logger.info("A Group universe: %d symbols (all strategies)", len(nifty200_symbols))

    universe_by_symbol: dict[str, UniverseStockEntry] = {s: UniverseStockEntry(symbol=s) for s in nifty200_symbols}
    nifty200_set = set(nifty200_symbols)

    semaphore = asyncio.Semaphore(max_concurrent_stock_calls)
    all_results: list[StockAnalysisResult] = []
    strategy_signals: dict[str, list[StrategySignal]] = {name: [] for name in ALL_SIGNAL_STRATEGY_NAMES}
    # Reuse across universes: every NIFTY 200 symbol is also in NIFTY 500 in
    # this project's real lists, so fetching it once for the 5-strategy pass
    # and reusing that same result/OHLCV for Value Buy avoids a second Angel
    # One call per overlapping symbol (spec: optimize API calls via reuse).
    analyzed_cache: dict[str, tuple[StockAnalysisResult, pd.DataFrame]] = {}

    async def process_nifty200(symbol: str) -> None:
        entry = universe_by_symbol[symbol]
        async with semaphore:
            result, ohlcv, error_reason = await _fetch_and_analyze(angelone_provider, symbol, config, stock_history_days)
            if result is not None and ohlcv is not None:
                analyzed_cache[symbol] = (result, ohlcv)
                all_results.append(result)
                entry.current_price = result.current_price
                entry.daily_rsi = result.daily.rsi
                entry.weekly_rsi = result.weekly.rsi
                entry.monthly_rsi = result.monthly.rsi
                entry.data_source = "ANGEL_ONE"
                entry.status = "OK"
                data_source_summary["ANGEL_ONE"] = data_source_summary.get("ANGEL_ONE", 0) + 1

                for name, signal in (
                    ("Strategy One", evaluate_strategy_one(result)),
                    ("GFS", evaluate_gfs(result, multi_strategy_config.gfs)),
                    ("Advanced GFS", evaluate_advanced_gfs(result, multi_strategy_config.advanced_gfs)),
                    ("PRD", evaluate_prd(result, ohlcv, multi_strategy_config.prd)),
                    ("NRD", evaluate_nrd(result, multi_strategy_config.nrd)),
                ):
                    if signal.qualifies:
                        signal.extra["current_price"] = result.current_price
                        signal.extra["data_source"] = "ANGEL_ONE"
                        strategy_signals[name].append(signal)
            else:
                failed_symbols.append(symbol)
                errors.append(f"{symbol}: {error_reason}")
                entry.status = "DATA_UNAVAILABLE"
                entry.status_reason = error_reason

    async def process_value_buy(symbol: str) -> None:
        async with semaphore:
            if symbol in analyzed_cache:
                result, ohlcv = analyzed_cache[symbol]
            else:
                result, ohlcv, error_reason = await _fetch_and_analyze(angelone_provider, symbol, config, stock_history_days)
                if result is None or ohlcv is None:
                    if symbol not in nifty200_set:
                        # Only count/report failures for symbols exclusive to
                        # the NIFTY 500 Value-Buy-only universe — NIFTY 200
                        # overlap failures are already recorded once above.
                        failed_symbols.append(symbol)
                        errors.append(f"{symbol}: {error_reason}")
                    return
                data_source_summary["ANGEL_ONE"] = data_source_summary.get("ANGEL_ONE", 0) + 1

            signal = evaluate_value_buy(result, ohlcv, multi_strategy_config.value_buy)
            if signal.qualifies:
                signal.extra["current_price"] = result.current_price
                signal.extra["data_source"] = "ANGEL_ONE"
                strategy_signals["Value Buy"].append(signal)

    await asyncio.gather(*(process_nifty200(s) for s in nifty200_symbols))
    await asyncio.gather(*(process_value_buy(s) for s in nifty500_symbols))

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
        universe_requested=len(nifty200_symbols),
        universe_returned=len(nifty200_symbols),
        universe_complete=True,
        value_buy_universe_requested=len(nifty500_symbols),
        value_buy_universe_returned=len(nifty500_symbols),
        stocks_scanned=len(nifty200_symbols) + len([s for s in nifty500_symbols if s not in nifty200_set]),
        stocks_failed=len(failed_symbols),
        failed_symbols=failed_symbols,
        all_results=all_results,
        qualifying_results=qualifying_results,
        top10=top10,
        top3=top3,
        best=best,
        nifty200_universe=list(universe_by_symbol.values()),
        strategy_signals=strategy_signals,
        data_source_summary=data_source_summary,
        errors=errors,
    )
