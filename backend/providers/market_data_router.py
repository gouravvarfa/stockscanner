"""
Angel One is the ONLY market-data provider in this project (Tapetide has
been removed entirely — see the Excel-based universe rewrite). This module
is kept as a small seam between the strategy/screener layer and Angel One
so callers ask for data by requirement (symbol + timeframe/kind) rather than
reaching into AngelOneProvider directly — useful if another provider is
ever added later, but there is no provider selection/fallback logic here
anymore since there is nothing to fall back to or choose between.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

import pandas as pd

from backend.providers.angelone_provider import AngelOneProvider

logger = logging.getLogger("scanner.data_router")

DataKind = Literal["daily", "15m", "1h", "future_daily"]

_INTERVAL_FOR_KIND = {"15m": "FIFTEEN_MINUTE", "1h": "ONE_HOUR"}


class DataUnavailableError(RuntimeError):
    pass


@dataclass
class DataSourceResult:
    data: pd.DataFrame
    data_source: str = "ANGEL_ONE"


class MarketDataRouter:
    def __init__(self, angelone_provider: AngelOneProvider) -> None:
        self._angelone = angelone_provider

    async def get_candles(self, symbol: str, kind: DataKind, days: int, strategy_name: str = "") -> DataSourceResult:
        logger.info("[DATA] provider=ANGEL_ONE strategy=%s symbol=%s kind=%s", strategy_name, symbol, kind)

        if kind == "future_daily":
            match = await self._angelone.resolve_stock_future(symbol)
            if match is None:
                raise DataUnavailableError(f"Angel One has no listed stock future for '{symbol}'.")
            data = await self._angelone.get_intraday_ohlc(match.exch_seg, match.token, "ONE_DAY", days)
            return DataSourceResult(data)

        if kind in ("15m", "1h"):
            match = await self._angelone.resolve_equity(symbol)
            if match is None:
                match = await self._angelone.resolve_index(symbol)
            if match is None:
                raise DataUnavailableError(f"Angel One has no equity/index listing for '{symbol}'.")
            data = await self._angelone.get_intraday_ohlc(match.exch_seg, match.token, _INTERVAL_FOR_KIND[kind], days)
            return DataSourceResult(data)

        # "daily"
        match = await self._angelone.resolve_equity(symbol)
        if match is None:
            raise DataUnavailableError(f"Angel One has no equity listing for '{symbol}'.")
        data = await self._angelone.get_intraday_ohlc(match.exch_seg, match.token, "ONE_DAY", days)
        return DataSourceResult(data)


async def fetch_daily_ohlcv(angelone: AngelOneProvider, symbol: str, days: int) -> pd.DataFrame:
    """Shared helper for the main scan pipeline (scan_service.py) — one equity resolve + one candle fetch."""
    match = await angelone.resolve_equity(symbol)
    if match is None:
        raise DataUnavailableError(f"Angel One has no equity listing for '{symbol}'.")
    return await angelone.get_intraday_ohlc(match.exch_seg, match.token, "ONE_DAY", days)
