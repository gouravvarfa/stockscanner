from __future__ import annotations

import asyncio
import datetime as dt
import logging
from dataclasses import dataclass, field
from typing import Callable

from backend.config.expiry_level_1_config import ExpiryLevel1Config
from backend.indicators.rsi import rsi
from backend.providers.market_data_router import MarketDataRouter
from backend.services import angelone_credential_store, universe_loader
from backend.strategies.expiry_level_1 import ExpiryLevel1Signal, detect_expiry_level_1_signal

logger = logging.getLogger("scanner.expiry_scan_service")

INDEX_NAMES = ["NIFTY", "BANKNIFTY"]


@dataclass
class ExpiryLevel1Outcome:
    started_at: dt.datetime
    finished_at: dt.datetime
    execution_seconds: float
    angelone_configured: bool
    index_signals: list[ExpiryLevel1Signal]
    stock_signals: list[ExpiryLevel1Signal]
    symbols_scanned: int
    symbols_failed: int
    failed_symbols: list[str]
    data_source_summary: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


async def _evaluate_one(
    router: MarketDataRouter,
    symbol: str,
    instrument_type: str,
    name: str,
    sector: str | None,
    config: ExpiryLevel1Config,
    data_source_summary: dict[str, int],
) -> ExpiryLevel1Signal | None:
    result_15m = await router.get_candles(symbol, "15m", config.intraday_lookback_days, strategy_name="Expiry Level 1")
    # Angel One's historical-candle endpoint enforces a strict per-second rate
    # limit; firing the 1h call immediately after the 15m one (and doing this
    # back-to-back across multiple symbols) was tripping it, surfacing as
    # intermittent "HTTP 403 non-JSON response" failures on whichever call
    # happened to land in the throttled window — not a real data problem.
    await asyncio.sleep(0.35)
    result_1h = await router.get_candles(symbol, "1h", config.intraday_lookback_days, strategy_name="Expiry Level 1")

    for result in (result_15m, result_1h):
        data_source_summary[result.data_source] = data_source_summary.get(result.data_source, 0) + 1

    ohlc_15m, ohlc_1h = result_15m.data, result_1h.data
    if ohlc_15m.empty or ohlc_1h.empty:
        return None

    rsi_15m = rsi(ohlc_15m["close"], period=config.rsi_period)
    rsi_1h = rsi(ohlc_1h["close"], period=config.rsi_period)

    return detect_expiry_level_1_signal(symbol, instrument_type, name, sector, rsi_15m, rsi_1h, config)


async def run_expiry_level_1_scan(
    market_data_router: MarketDataRouter,
    config: ExpiryLevel1Config,
    max_stocks: int = 40,
    max_concurrent: int = 3,
    on_progress: Callable[[str, bool, str | None], None] | None = None,
) -> ExpiryLevel1Outcome:
    """`on_progress(symbol, success, error)` — optional, called once per
    index/stock as it finishes. Defaults to None (existing callers/tests
    unaffected)."""
    started_at = dt.datetime.utcnow()
    errors: list[str] = []
    failed_symbols: list[str] = []
    data_source_summary: dict[str, int] = {}

    if not angelone_credential_store.is_configured():
        finished_at = dt.datetime.utcnow()
        return ExpiryLevel1Outcome(
            started_at=started_at,
            finished_at=finished_at,
            execution_seconds=(finished_at - started_at).total_seconds(),
            angelone_configured=False,
            index_signals=[],
            stock_signals=[],
            symbols_scanned=0,
            symbols_failed=0,
            failed_symbols=[],
            errors=[
                "Angel One is not connected — connect it from the Expiry Level 1 page (or set "
                "ANGELONE_API_KEY/CLIENT_CODE/PIN/TOTP_SECRET in .env). Expiry Level 1 requires intraday "
                "data, which only Angel One provides in this project."
            ],
        )

    index_signals: list[ExpiryLevel1Signal] = []
    for i, index_name in enumerate(INDEX_NAMES):
        if i > 0:
            await asyncio.sleep(0.35)  # same Angel One rate-limit pacing as between the 15m/1h calls
        try:
            signal = await _evaluate_one(
                market_data_router, index_name, "INDEX", index_name, None, config, data_source_summary,
            )
            if signal is not None:
                index_signals.append(signal)
            if on_progress is not None:
                on_progress(index_name, True, None)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Index %s failed: %s", index_name, exc)
            failed_symbols.append(index_name)
            errors.append(f"{index_name}: {exc}")
            if on_progress is not None:
                on_progress(index_name, False, str(exc))

    # Index signals need only Angel One and must not be blocked by a
    # universe-fetch failure — so it's isolated here, not fatal to the whole
    # scan.
    candidates: list[str] = []
    try:
        candidates = universe_loader.load_a_group_universe()[:max_stocks]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Stock universe fetch failed, continuing with index-only results: %s", exc)
        errors.append(f"Stock universe unavailable: {exc}")

    semaphore = asyncio.Semaphore(max_concurrent)
    stock_signals: list[ExpiryLevel1Signal] = []

    async def process(symbol: str) -> None:
        async with semaphore:
            try:
                signal = await _evaluate_one(
                    market_data_router, symbol, "STOCK", symbol, None, config, data_source_summary,
                )
                if signal is not None:
                    stock_signals.append(signal)
                if on_progress is not None:
                    on_progress(symbol, True, None)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Stock %s failed: %s", symbol, exc)
                failed_symbols.append(symbol)
                errors.append(f"{symbol}: {exc}")
                if on_progress is not None:
                    on_progress(symbol, False, str(exc))

    await asyncio.gather(*(process(s) for s in candidates))

    finished_at = dt.datetime.utcnow()
    return ExpiryLevel1Outcome(
        started_at=started_at,
        finished_at=finished_at,
        execution_seconds=(finished_at - started_at).total_seconds(),
        angelone_configured=True,
        index_signals=index_signals,
        stock_signals=stock_signals,
        symbols_scanned=len(INDEX_NAMES) + len(candidates),
        symbols_failed=len(failed_symbols),
        failed_symbols=failed_symbols,
        data_source_summary=data_source_summary,
        errors=errors,
    )
