from __future__ import annotations

import asyncio
import datetime as dt
import logging
from dataclasses import dataclass, field
from typing import Callable

from backend.config.expiry_level_5_config import ExpiryLevel5Config
from backend.providers.market_data_router import DataUnavailableError, MarketDataRouter
from backend.services import angelone_credential_store, universe_loader
from backend.strategies.expiry_level_5 import ExpiryLevel5Signal, detect_expiry_level_5_signal

logger = logging.getLogger("scanner.expiry_level_5_scan_service")


@dataclass
class ExpiryLevel5Outcome:
    started_at: dt.datetime
    finished_at: dt.datetime
    execution_seconds: float
    angelone_configured: bool
    signals: list[ExpiryLevel5Signal]
    symbols_scanned: int
    symbols_failed: int
    failed_symbols: list[str]
    data_source_summary: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


async def run_expiry_level_5_scan(
    market_data_router: MarketDataRouter,
    config: ExpiryLevel5Config,
    max_stocks: int = 40,
    max_concurrent: int = 3,
    on_progress: Callable[[str, bool, str | None], None] | None = None,
) -> ExpiryLevel5Outcome:
    """`on_progress(symbol, success, error)` — optional, called once per
    stock as it finishes. Defaults to None (existing callers/tests
    unaffected)."""
    started_at = dt.datetime.utcnow()
    errors: list[str] = []
    failed_symbols: list[str] = []
    data_source_summary: dict[str, int] = {}

    if not angelone_credential_store.is_configured():
        finished_at = dt.datetime.utcnow()
        return ExpiryLevel5Outcome(
            started_at=started_at,
            finished_at=finished_at,
            execution_seconds=(finished_at - started_at).total_seconds(),
            angelone_configured=False,
            signals=[],
            symbols_scanned=0,
            symbols_failed=0,
            failed_symbols=[],
            errors=[
                "Angel One is not connected — connect it from the Expiry Level 1/5 page. "
                "Expiry Level 5 requires stock-future data, which only Angel One provides in this project."
            ],
        )

    candidates: list[str] = []
    try:
        candidates = universe_loader.load_a_group_universe()[:max_stocks]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Stock universe fetch failed: %s", exc)
        errors.append(f"Stock universe unavailable: {exc}")

    semaphore = asyncio.Semaphore(max_concurrent)
    signals: list[ExpiryLevel5Signal] = []

    async def process(symbol: str) -> None:
        async with semaphore:
            try:
                result = await market_data_router.get_candles(
                    symbol, "future_daily", config.lookback_days, strategy_name="Expiry Level 5"
                )
                data_source_summary[result.data_source] = data_source_summary.get(result.data_source, 0) + 1

                if result.data.empty:
                    if on_progress is not None:
                        on_progress(symbol, True, None)
                    return

                signal = detect_expiry_level_5_signal(symbol, result.data, config)
                if signal is not None:
                    signals.append(signal)
                if on_progress is not None:
                    on_progress(symbol, True, None)
            except DataUnavailableError:
                # Not every stock has a listed future — an expected, common
                # outcome, not a scan failure, so it's skipped silently.
                if on_progress is not None:
                    on_progress(symbol, True, None)
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning("Stock future %s failed: %s", symbol, exc)
                failed_symbols.append(symbol)
                errors.append(f"{symbol}: {exc}")
                if on_progress is not None:
                    on_progress(symbol, False, str(exc))

    await asyncio.gather(*(process(s) for s in candidates))

    finished_at = dt.datetime.utcnow()
    return ExpiryLevel5Outcome(
        started_at=started_at,
        finished_at=finished_at,
        execution_seconds=(finished_at - started_at).total_seconds(),
        angelone_configured=True,
        signals=signals,
        symbols_scanned=len(candidates),
        symbols_failed=len(failed_symbols),
        failed_symbols=failed_symbols,
        data_source_summary=data_source_summary,
        errors=errors,
    )
