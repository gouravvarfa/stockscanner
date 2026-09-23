"""
Cup Breakout scan orchestration — completely separate from
backend/services/scan_service.py's run_full_scan (PRD/NRD/GFS/Advanced
GFS/System One/Value Buy). Reuses:
  - the same A-Group universe (backend/services/universe_loader.py)
  - the same Angel One provider/authentication (backend/providers/angelone_provider.py)
  - the same FUTURE/EQUITY classifier (backend/services/instrument_classifier.py)
  - the same generic background-job machinery (backend/services/scan_job_manager.py),
    wired up in backend/api/scan_jobs.py under scan_type "cup_breakout"

Never imports or calls anything from strategies/prd.py, nrd.py, gfs.py,
advanced_gfs.py, strategy_one.py, or value_buy.py.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from backend.config.cup_config import CupConfig, DEFAULT_CUP_CONFIG
from backend.providers.angelone_provider import AngelOneProvider
from backend.providers.cup_history import CupDataUnavailableError, fetch_cup_history
from backend.services import universe_loader
from backend.services.instrument_classifier import get_instrument_type
from backend.strategies.cup import QUALIFYING_STATUSES, detect_cup
from backend.strategies.types import StrategySignal

logger = logging.getLogger("scanner.cup_scan_service")

# Each stock costs several sequential, delayed Angel One requests (chunked
# multi-year history) — a low concurrency keeps this well under Angel One's
# rate limit even with several "lanes" running at once, per the existing
# per-job-semaphore pattern in scan_service.py (never a shared cross-job
# limiter — see that module's DEFAULT_MAX_CONCURRENT_PER_JOB_FETCHES comment).
DEFAULT_MAX_CONCURRENT_CUP_FETCHES = 2


@dataclass
class CupScanOutcome:
    started_at: dt.datetime
    finished_at: dt.datetime
    execution_seconds: float
    stocks_scanned: int
    stocks_failed: int
    failed_symbols: list[str]
    results: list[dict[str, Any]] = field(default_factory=list)  # only QUALIFYING_STATUSES


def _cup_result_to_signal(symbol: str, instrument_type: str, cup_result: dict[str, Any]) -> StrategySignal:
    """Reuses the existing StrategySignal shape (same one PRD/NRD/GFS use)
    purely so this scan can go through the SAME generic ScanJob.record_result
    plumbing (partial/progress polling, IndexedDB history mapping, etc.)
    without that plumbing needing to know anything Cup-specific. RSI fields
    are not applicable to Cup and are always None."""
    extra = dict(cup_result)
    extra["current_price"] = cup_result.get("latest_monthly_close")
    extra["data_source"] = "ANGEL_ONE"
    status = cup_result["status"]
    return StrategySignal(
        strategy="CUP",
        symbol=symbol,
        qualifies=status in QUALIFYING_STATUSES,
        signal_date=None,
        daily_rsi=None,
        weekly_rsi=None,
        monthly_rsi=None,
        conditions={},
        explanation=f"Cup Breakout: {status} (breakout level {cup_result.get('potential_breakout_level')})",
        extra=extra,
    )


async def run_cup_scan(
    angelone_provider: AngelOneProvider,
    config: CupConfig = DEFAULT_CUP_CONFIG,
    max_concurrent_fetches: int = DEFAULT_MAX_CONCURRENT_CUP_FETCHES,
    on_progress: Callable[[str, bool, str | None], None] | None = None,
    on_result: Callable[[str, list[tuple[str, StrategySignal]]], None] | None = None,
) -> CupScanOutcome:
    started_at = dt.datetime.utcnow()
    universe = universe_loader.load_a_group_universe()
    logger.info("Cup Breakout scan: %d symbols (same A Group universe)", len(universe))

    semaphore = asyncio.Semaphore(max_concurrent_fetches)
    results: list[dict[str, Any]] = []
    failed_symbols: list[str] = []
    stocks_scanned = 0

    async def process(symbol: str) -> None:
        nonlocal stocks_scanned
        instrument_type = get_instrument_type(symbol)
        try:
            async with semaphore:
                daily_ohlcv = await fetch_cup_history(angelone_provider, symbol, config)
            # CPU-bound detection kept off the semaphore (no network here) —
            # cheap enough (~120 monthly bars) not to need its own thread pool.
            cup_result = detect_cup(daily_ohlcv, config)
        except CupDataUnavailableError as exc:
            failed_symbols.append(symbol)
            if on_progress is not None:
                on_progress(symbol, False, str(exc))
            return
        except Exception as exc:  # noqa: BLE001 — one bad stock must never stop the whole scan
            logger.warning("Cup Breakout: %s failed: %s", symbol, exc)
            failed_symbols.append(symbol)
            if on_progress is not None:
                on_progress(symbol, False, str(exc))
            return

        stocks_scanned += 1
        cup_result["symbol"] = symbol
        cup_result["instrument_type"] = instrument_type
        cup_result["updated_at"] = dt.datetime.utcnow().isoformat()

        qualifying: list[tuple[str, StrategySignal]] = []
        if cup_result["status"] in QUALIFYING_STATUSES:
            results.append(cup_result)
            signal = _cup_result_to_signal(symbol, instrument_type, cup_result)
            qualifying.append(("CUP", signal))

        if on_result is not None:
            on_result(symbol, qualifying)
        if on_progress is not None:
            on_progress(symbol, True, None)

    # Same pattern as scan_service.py's run_full_scan: scheduling all 615
    # coroutines is cheap (asyncio tasks, not open connections) — the
    # semaphore above caps REAL concurrent network/memory work to
    # `max_concurrent_fetches`, which is what actually matters for rate
    # limiting and memory pressure, not the coroutine count.
    await asyncio.gather(*(process(symbol) for symbol in universe))

    finished_at = dt.datetime.utcnow()
    return CupScanOutcome(
        started_at=started_at,
        finished_at=finished_at,
        execution_seconds=(finished_at - started_at).total_seconds(),
        stocks_scanned=stocks_scanned,
        stocks_failed=len(failed_symbols),
        failed_symbols=failed_symbols,
        results=results,
    )
