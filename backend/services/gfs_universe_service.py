"""
"All Stocks" list for the GFS-family backtest pages: every stock in the A Group
universe whose LATEST daily candle satisfies the strategy's backtest setup
(the same rule and config the backtest page uses, via gfs_setup_flags), with the
date range of the data that was read and its current RSIs.

Fetching ~600 stocks from Angel One takes minutes, so it runs as a background
task per strategy; the page starts it, polls its progress and reads the rows.
Rows are streamed: a stock is added to the list the moment it qualifies, so the
page fills in while the scan is still running (always sorted by company name).
The last finished result is cached in memory and served until it is refreshed
or older than CACHE_TTL.
"""
from __future__ import annotations

import asyncio
import bisect
import contextlib
import datetime as dt
import logging
from dataclasses import dataclass, field

from backend.config.strategy_config import (
    DEFAULT_ADVANCED_GFS_BACKTEST_CONFIG,
    DEFAULT_GFS50_BACKTEST_CONFIG,
    DEFAULT_GFS_BACKTEST_CONFIG,
    GFSBacktestConfig,
)
from backend.providers.angelone_provider import AngelOneProvider
from backend.providers.market_data_router import MONTHLY_RSI_LOOKBACK_DAYS, fetch_daily_ohlcv
from backend.services import universe_loader
from backend.strategies.gfs_backtest import gfs_setup_flags

logger = logging.getLogger("scanner.gfs_universe")

CONFIGS: dict[str, GFSBacktestConfig] = {
    "gfs": DEFAULT_GFS_BACKTEST_CONFIG,
    "advanced": DEFAULT_ADVANCED_GFS_BACKTEST_CONFIG,
    "gfs50": DEFAULT_GFS50_BACKTEST_CONFIG,
}

CACHE_TTL = dt.timedelta(hours=24)
# Angel One's historical endpoint is rate limited per second (see scan_service.py);
# the same low concurrency the main scan uses per job.
MAX_CONCURRENT_FETCHES = 2
PER_STOCK_TIMEOUT_SECONDS = 75.0
MIN_CANDLES = 60


@dataclass
class UniverseRow:
    symbol: str
    company_name: str
    data_from: dt.date
    data_to: dt.date
    close: float
    daily_rsi: float | None
    weekly_rsi: float | None
    monthly_rsi: float | None
    in_setup_since: dt.date  # first day of the unbroken run of setup days ending on data_to


@dataclass
class UniverseState:
    status: str = "idle"  # idle | running | done | error
    total: int = 0
    processed: int = 0
    failed: int = 0
    rows: list[UniverseRow] = field(default_factory=list)
    started_at: dt.datetime | None = None
    finished_at: dt.datetime | None = None
    error: str | None = None


_states: dict[str, UniverseState] = {}
_tasks: dict[str, asyncio.Task] = {}

# A user-triggered backtest shares Angel One's rate limit with this long background
# scan; competing for it makes the backtest crawl (throttled calls are retried with
# backoff). While any backtest is running, the scan holds back NEW fetches.
_backtests_running = 0
_YIELD_POLL_SECONDS = 0.25


@contextlib.contextmanager
def backtest_priority():
    """Wrap a user-triggered backtest: the all-stocks scan pauses until it is done."""
    global _backtests_running
    _backtests_running += 1
    try:
        yield
    finally:
        _backtests_running -= 1


async def _yield_to_backtests() -> None:
    while _backtests_running > 0:
        await asyncio.sleep(_YIELD_POLL_SECONDS)


def get_state(variant: str) -> UniverseState:
    return _states.setdefault(variant, UniverseState())


def _nan_to_none(v: float) -> float | None:
    return None if v != v else float(v)


def evaluate_stock(symbol: str, ohlcv, config: GFSBacktestConfig) -> UniverseRow | None:
    """A row if the latest candle satisfies the setup, else None. Pure (no I/O)."""
    if ohlcv is None or ohlcv.empty or len(ohlcv) < MIN_CANDLES:
        return None
    df = ohlcv.sort_index()
    setup, daily, weekly, monthly = gfs_setup_flags(df, config)
    if not setup or not setup[-1]:
        return None
    start = len(setup) - 1
    while start > 0 and setup[start - 1]:
        start -= 1
    return UniverseRow(
        symbol=symbol,
        company_name=universe_loader.company_name_for(symbol) or symbol,
        data_from=df.index[0].date(),
        data_to=df.index[-1].date(),
        close=float(df["close"].iloc[-1]),
        daily_rsi=_nan_to_none(daily[-1]),
        weekly_rsi=_nan_to_none(weekly[-1]),
        monthly_rsi=_nan_to_none(monthly[-1]),
        in_setup_since=df.index[start].date(),
    )


async def _run(variant: str, provider: AngelOneProvider, state: UniverseState) -> None:
    config = CONFIGS[variant]
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_FETCHES)

    async def one(symbol: str) -> None:
        try:
            async with semaphore:
                await _yield_to_backtests()
                ohlcv = await asyncio.wait_for(
                    fetch_daily_ohlcv(provider, symbol, MONTHLY_RSI_LOOKBACK_DAYS), timeout=PER_STOCK_TIMEOUT_SECONDS
                )
            row = await asyncio.to_thread(evaluate_stock, symbol, ohlcv, config)
            if row is not None:
                # Streamed: visible to the next poll the moment it qualifies, kept sorted by
                # company name. This runs on the event loop, so it never races a reader.
                bisect.insort(state.rows, row, key=lambda r: r.company_name.lower())
        except Exception as exc:  # noqa: BLE001 - one bad symbol must never stop the whole list
            state.failed += 1
            logger.warning("%s: %s", symbol, exc)
        finally:
            state.processed += 1

    try:
        await asyncio.gather(*(one(s) for s in universe_loader.load_a_group_universe()))
        state.status = "done"
    except Exception as exc:  # noqa: BLE001
        state.status, state.error = "error", str(exc)
    finally:
        state.finished_at = dt.datetime.utcnow()


def start(variant: str, provider: AngelOneProvider, fresh: bool = False) -> UniverseState:
    """Start a run unless one is already running or a fresh-enough result is cached."""
    state = get_state(variant)
    if state.status == "running":
        return state
    cached = (
        state.status == "done" and state.finished_at is not None
        and dt.datetime.utcnow() - state.finished_at < CACHE_TTL
    )
    if cached and not fresh:
        return state
    new = UniverseState(
        status="running", total=len(universe_loader.load_a_group_universe()), started_at=dt.datetime.utcnow(),
    )
    _states[variant] = new
    _tasks[variant] = asyncio.create_task(_run(variant, provider, new))
    return new
