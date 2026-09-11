"""
Capability-based market-data router. Strategies/services ask for data by
requirement (symbol + timeframe + kind), never by provider name directly —
this module decides TAPETIDE vs ANGEL_ONE based on the selected mode and each
provider's verified capabilities (backend/providers/capabilities.py).

No data mixing: one call here returns data from exactly ONE provider for the
whole requested series — never a blend.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal

import pandas as pd

from backend.config.data_source_config import DataSourceMode
from backend.providers import call_metrics
from backend.providers.angelone_provider import AngelOneNotConfiguredError, AngelOneProvider
from backend.providers.base import MarketDataProvider
from backend.providers.capabilities import ANGEL_ONE_CAPABILITIES, TAPETIDE_CAPABILITIES, capability_for_timeframe

logger = logging.getLogger("scanner.data_router")

DataKind = Literal["daily", "15m", "1h", "future_daily"]


class DataUnavailableError(RuntimeError):
    pass


@dataclass
class DataSourceResult:
    data: pd.DataFrame
    data_source: str  # "TAPETIDE" | "ANGEL_ONE"
    selection_mode: str  # "AUTO" | "TAPETIDE" | "ANGEL_ONE"
    fallback_used: bool
    fallback_reason: str | None


_KIND_TIMEFRAME = {"daily": "1d", "15m": "15m", "1h": "1h", "future_daily": "1d"}
# Only Angel One is wired for these kinds in this project (Tapetide has no
# intraday history and no futures concept at all — verified, see capabilities.py).
_ANGEL_ONLY_KINDS = {"15m", "1h", "future_daily"}


class MarketDataRouter:
    def __init__(self, tapetide_provider: MarketDataProvider, angelone_provider: AngelOneProvider) -> None:
        self._tapetide = tapetide_provider
        self._angelone = angelone_provider

    async def _fetch_tapetide_daily(self, symbol: str, days: int) -> pd.DataFrame:
        return await self._tapetide.get_stock_ohlcv(symbol, days=days)

    async def _fetch_angelone_daily(self, symbol: str, days: int) -> pd.DataFrame:
        match = await self._angelone.resolve_equity(symbol)
        if match is None:
            raise DataUnavailableError(f"Angel One has no equity listing for '{symbol}'.")
        return await self._angelone.get_intraday_ohlc(match.exch_seg, match.token, "ONE_DAY", days)

    async def _fetch_angelone_intraday(self, symbol: str, timeframe: str, days: int) -> pd.DataFrame:
        match = await self._angelone.resolve_equity(symbol)
        if match is None:
            match = await self._angelone.resolve_index(symbol)
        if match is None:
            raise DataUnavailableError(f"Angel One has no equity/index listing for '{symbol}'.")
        interval = "FIFTEEN_MINUTE" if timeframe == "15m" else "ONE_HOUR"
        return await self._angelone.get_intraday_ohlc(match.exch_seg, match.token, interval, days)

    async def _fetch_angelone_future_daily(self, symbol: str, days: int) -> pd.DataFrame:
        match = await self._angelone.resolve_stock_future(symbol)
        if match is None:
            raise DataUnavailableError(f"Angel One has no listed stock future for '{symbol}'.")
        return await self._angelone.get_intraday_ohlc(match.exch_seg, match.token, "ONE_DAY", days)

    async def get_candles(
        self, symbol: str, kind: DataKind, days: int, mode: DataSourceMode, strategy_name: str = ""
    ) -> DataSourceResult:
        timeframe = _KIND_TIMEFRAME[kind]
        angel_only = kind in _ANGEL_ONLY_KINDS

        async def _fetch_angel() -> pd.DataFrame:
            if kind == "future_daily":
                return await self._fetch_angelone_future_daily(symbol, days)
            if kind in ("15m", "1h"):
                return await self._fetch_angelone_intraday(symbol, timeframe, days)
            return await self._fetch_angelone_daily(symbol, days)

        logger.info("[DATA] mode=%s strategy=%s symbol=%s timeframe=%s", mode.upper(), strategy_name, symbol, timeframe)

        if mode == "tapetide":
            if angel_only or not capability_for_timeframe(TAPETIDE_CAPABILITIES, timeframe):
                msg = f"Tapetide selected, but required {timeframe} historical candles are not available from Tapetide."
                logger.info("[DATA] provider=TAPETIDE unavailable reason=%s", msg)
                raise DataUnavailableError(msg)
            data = await self._fetch_tapetide_daily(symbol, days)
            logger.info("[DATA] provider=TAPETIDE fallback=false")
            return DataSourceResult(data, "TAPETIDE", "TAPETIDE", False, None)

        if mode == "angel_one":
            if not capability_for_timeframe(ANGEL_ONE_CAPABILITIES, timeframe):
                msg = f"Angel One selected, but required {timeframe} historical candles are not available from Angel One."
                logger.info("[DATA] provider=ANGEL_ONE unavailable reason=%s", msg)
                raise DataUnavailableError(msg)
            data = await _fetch_angel()
            logger.info("[DATA] provider=ANGEL_ONE fallback=false")
            return DataSourceResult(data, "ANGEL_ONE", "ANGEL_ONE", False, None)

        # AUTO: capability-first routing (never blind-trial a provider we
        # already know lacks the timeframe — spec section 30), then
        # failure-based fallback if the chosen provider's live call errors.
        if angel_only or not capability_for_timeframe(TAPETIDE_CAPABILITIES, timeframe):
            try:
                data = await _fetch_angel()
            except (DataUnavailableError, AngelOneNotConfiguredError) as exc:
                raise DataUnavailableError(
                    f"Required {timeframe} candles for '{symbol}' are unavailable: Tapetide does not support "
                    f"this timeframe and Angel One failed ({exc})."
                ) from exc
            logger.info("[DATA] provider=ANGEL_ONE fallback=false (Tapetide lacks %s capability)", timeframe)
            return DataSourceResult(
                data, "ANGEL_ONE", "AUTO", True, f"Tapetide does not provide {timeframe} historical candles."
            )

        try:
            data = await self._fetch_tapetide_daily(symbol, days)
            logger.info("[DATA] provider=TAPETIDE fallback=false")
            return DataSourceResult(data, "TAPETIDE", "AUTO", False, None)
        except Exception as exc:  # noqa: BLE001 — genuinely any Tapetide failure triggers fallback here
            logger.warning("[DATA] provider=TAPETIDE unavailable reason=%s", exc)
            try:
                data = await _fetch_angel()
            except Exception as angel_exc:  # noqa: BLE001
                raise DataUnavailableError(
                    f"Neither provider could supply daily candles for '{symbol}': "
                    f"Tapetide failed ({exc}); Angel One failed ({angel_exc})."
                ) from angel_exc
            reason = f"Tapetide failed for '{symbol}': {exc}"
            logger.info("[DATA] provider=ANGEL_ONE fallback=true reason=%s", reason)
            call_metrics.record_fallback()
            return DataSourceResult(data, "ANGEL_ONE", "AUTO", True, reason)
