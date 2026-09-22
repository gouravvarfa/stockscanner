from __future__ import annotations

import asyncio
import concurrent.futures
import datetime as dt
import logging
from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

from backend.config.multi_strategy_config import DEFAULT_MULTI_STRATEGY_CONFIG, MultiStrategyConfig
from backend.config.strategy_config import StrategyConfig
from backend.providers.angelone_provider import AngelOneProvider
from backend.providers.market_data_router import MONTHLY_RSI_LOOKBACK_DAYS, fetch_daily_ohlcv
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
# Tapetide free tier this replaced). This is the SAME depth chart_service.py
# requests for its "1M" timeframe (MONTHLY_RSI_LOOKBACK_DAYS) — the scan's
# single daily-OHLCV fetch already covers daily/weekly/monthly, so reusing
# that shared constant here (rather than a separately-tuned number) means
# the scanner's monthly RSI can never drift from what the chart shows for
# the same stock, with no extra Angel One call.
STOCK_HISTORY_DAYS = MONTHLY_RSI_LOOKBACK_DAYS

PRD_FORMING_KEY = "PRD Forming"
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


# A slow/hung stock must be isolated, not stall the whole scan: bounds one
# stock's whole Angel One fetch (resolve + candle call incl. its own retries).
PER_STOCK_FETCH_TIMEOUT_SECONDS = 75.0
# Angel One's candle endpoint throttles bursts (HTTP 403 non-JSON) — 4 in
# flight is the tested-safe level. CPU analysis runs OUTSIDE this limit.
DEFAULT_MAX_CONCURRENT_FETCHES = 4


async def _fetch_and_analyze(
    angelone_provider: AngelOneProvider,
    symbol: str,
    config: StrategyConfig,
    stock_history_days: int,
) -> tuple[StockAnalysisResult | None, pd.DataFrame | None, str | None]:
    """Returns (analysis_result_or_None, daily_ohlcv, error_reason_or_None)."""
    try:
        ohlcv = await asyncio.wait_for(
            fetch_daily_ohlcv(angelone_provider, symbol, stock_history_days),
            timeout=PER_STOCK_FETCH_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        return None, None, f"Timed out after {PER_STOCK_FETCH_TIMEOUT_SECONDS:.0f}s fetching market data"
    except Exception as exc:  # noqa: BLE001 — one bad symbol must never crash the whole scan
        return None, None, str(exc)

    # CPU-bound (indicators + divergence detection): run in a worker thread
    # so the event loop keeps serving API polls and other stocks' fetches.
    result = await asyncio.to_thread(analyze_stock, symbol, ohlcv, config)
    if result is None:
        return None, ohlcv, "Insufficient historical data (fewer than 60 daily bars)"
    return result, ohlcv, None


def _evaluate_all_strategies(
    result: StockAnalysisResult, ohlcv: pd.DataFrame, multi_strategy_config: MultiStrategyConfig, include_value_buy: bool
) -> list[tuple[str, StrategySignal]]:
    """All strategy evaluations for one stock, from the SAME already-fetched
    data (fetch once -> every strategy reuses it). Runs in a worker thread."""
    evaluated = [
        ("Strategy One", evaluate_strategy_one(result)),
        ("GFS", evaluate_gfs(result, multi_strategy_config.gfs)),
        ("Advanced GFS", evaluate_advanced_gfs(result, multi_strategy_config.advanced_gfs)),
        ("PRD", evaluate_prd(result, ohlcv, multi_strategy_config.prd)),
        ("NRD", evaluate_nrd(result, multi_strategy_config.nrd)),
    ]
    if include_value_buy:
        evaluated.append(("Value Buy", evaluate_value_buy(result, ohlcv, multi_strategy_config.value_buy)))
    qualifying = []
    for name, signal in evaluated:
        if name == "PRD" and not signal.qualifies and signal.extra.get("status") == "PRD_FORMING":
            # Developing (not confirmed) Positive Reversal: reported under its
            # OWN key so it is visible but never counted as a confirmed PRD.
            signal.extra["current_price"] = result.current_price
            signal.extra["data_source"] = "ANGEL_ONE"
            qualifying.append((PRD_FORMING_KEY, signal))
        if signal.qualifies:
            signal.extra["current_price"] = result.current_price
            signal.extra["data_source"] = "ANGEL_ONE"
            qualifying.append((name, signal))
    return qualifying


async def run_full_scan(
    angelone_provider: AngelOneProvider,
    config: StrategyConfig,
    stock_history_days: int = STOCK_HISTORY_DAYS,
    # Angel One's historical-candle endpoint enforces a strict per-second
    # rate limit (see the Expiry Level 1 pacing fix) — a large burst of
    # concurrent requests risks intermittent "HTTP 403 non-JSON response"
    # throttling, not a real data problem.
    max_concurrent_stock_calls: int = DEFAULT_MAX_CONCURRENT_FETCHES,
    multi_strategy_config: MultiStrategyConfig | None = None,
    on_progress: Callable[[str, bool, str | None], None] | None = None,
    on_result: Callable[[str, list[tuple[str, StrategySignal]]], None] | None = None,
) -> ScanOutcome:
    """
    `on_progress(symbol, success, error)` — optional, called once per symbol
    as it finishes (the A Group / "process_nifty200" pass, where the real
    Angel One work happens; Value Buy is evaluated inline in that same pass
    — see `_evaluate_all_strategies` — so the Value Buy pass below does no
    additional work for any symbol in this project's real universe).
    Defaults to None so every existing direct caller/test is unaffected.

    `on_result(symbol, qualifying_signals)` — optional, called the moment a
    stock finishes (all six strategies already evaluated from its single
    fetch), so callers can surface results progressively instead of waiting
    for the whole universe.
    """
    multi_strategy_config = multi_strategy_config or DEFAULT_MULTI_STRATEGY_CONFIG
    started_at = dt.datetime.utcnow()
    errors: list[str] = []
    failed_symbols: list[str] = []
    data_source_summary: dict[str, int] = {}

    # Every strategy — Value Buy included — now runs over the single BSE
    # "A Group" universe. Value Buy keeps its own symbol list variable (and
    # its own pass) so the two can diverge again without reshaping the scan,
    # but today they are the same list, so Value Buy is evaluated inline in
    # process_nifty200 for every symbol and this second pass does no work.
    nifty200_symbols = universe_loader.load_a_group_universe()
    nifty500_symbols = nifty200_symbols
    logger.info("A Group universe: %d symbols (all strategies)", len(nifty200_symbols))

    universe_by_symbol: dict[str, UniverseStockEntry] = {s: UniverseStockEntry(symbol=s) for s in nifty200_symbols}
    nifty200_set = set(nifty200_symbols)

    semaphore = asyncio.Semaphore(max_concurrent_stock_calls)
    # Bounds CPU-heavy work (analysis + strategy evaluation) to the SAME
    # concurrency as the Angel One fetch above. asyncio.to_thread's default
    # executor allows far more concurrent workers (min(32, cpu_count+4)) —
    # on a low-memory host, many stocks' full OHLCV frames + indicator
    # arrays alive in memory at once (independent of the fetch-side limit)
    # is what was exhausting memory and crashing the process mid-scan.
    cpu_pool = concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrent_stock_calls)
    loop = asyncio.get_running_loop()
    all_results: list[StockAnalysisResult] = []
    strategy_signals: dict[str, list[StrategySignal]] = {name: [] for name in [*ALL_SIGNAL_STRATEGY_NAMES, PRD_FORMING_KEY]}

    value_buy_set = set(nifty500_symbols)

    value_buy_done: set[str] = set()

    async def _fetch_and_analyze_unlimited(symbol: str):
        return await _fetch_and_analyze(angelone_provider, symbol, config, stock_history_days)

    async def process_nifty200(symbol: str) -> None:
        entry = universe_by_symbol[symbol]
        async with semaphore:  # limits only the Angel One fetch, not the CPU work
            result, ohlcv, error_reason = await _fetch_and_analyze_unlimited(symbol)
        if result is not None and ohlcv is not None:
            all_results.append(result)
            entry.current_price = result.current_price
            entry.daily_rsi = result.daily.rsi
            entry.weekly_rsi = result.weekly.rsi
            entry.monthly_rsi = result.monthly.rsi
            entry.data_source = "ANGEL_ONE"
            entry.status = "OK"
            data_source_summary["ANGEL_ONE"] = data_source_summary.get("ANGEL_ONE", 0) + 1

            qualifying = await loop.run_in_executor(
                cpu_pool, _evaluate_all_strategies, result, ohlcv, multi_strategy_config, symbol in value_buy_set
            )
            for name, signal in qualifying:
                strategy_signals[name].append(signal)
            if symbol in value_buy_set:
                value_buy_done.add(symbol)
            if on_result is not None:
                on_result(symbol, qualifying)
            if on_progress is not None:
                on_progress(symbol, True, None)
        else:
            failed_symbols.append(symbol)
            errors.append(f"{symbol}: {error_reason}")
            entry.status = "DATA_UNAVAILABLE"
            entry.status_reason = error_reason
            if on_progress is not None:
                on_progress(symbol, False, error_reason)

    async def process_value_buy(symbol: str) -> None:
        # Only symbols that were NOT part of the main pass. A symbol that
        # failed in the main pass is never re-fetched (that duplicate fetch
        # + its retry/backoff was what made the scan crawl after "615/615").
        if symbol in value_buy_done or symbol in nifty200_set:
            return
        async with semaphore:
            result, ohlcv, error_reason = await _fetch_and_analyze(angelone_provider, symbol, config, stock_history_days)
        if result is None or ohlcv is None:
            failed_symbols.append(symbol)
            errors.append(f"{symbol}: {error_reason}")
            return
        data_source_summary["ANGEL_ONE"] = data_source_summary.get("ANGEL_ONE", 0) + 1
        signal = await loop.run_in_executor(cpu_pool, evaluate_value_buy, result, ohlcv, multi_strategy_config.value_buy)
        if signal.qualifies:
            signal.extra["current_price"] = result.current_price
            signal.extra["data_source"] = "ANGEL_ONE"
            strategy_signals["Value Buy"].append(signal)
            if on_result is not None:
                on_result(symbol, [("Value Buy", signal)])

    try:
        await asyncio.gather(*(process_nifty200(s) for s in nifty200_symbols))
        await asyncio.gather(*(process_value_buy(s) for s in nifty500_symbols))
    finally:
        cpu_pool.shutdown(wait=False, cancel_futures=True)

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
