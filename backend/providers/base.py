"""
Provider interface — keeps the strategy/screener engine decoupled from any
one data vendor (spec section 2/3/31: other brokers/providers can be added
later without touching the scanner logic).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import pandas as pd


class MarketDataProvider(ABC):
    @abstractmethod
    async def get_universe(self, index_slug: str = "nifty-200") -> dict[str, Any]:
        """
        Real, current index constituents with sector tags. Never hardcoded.
        Returns {"stocks": [...], "requested": int, "returned": int, "complete": bool,
        "sources": [...]} — `complete` and the counts MUST be reported honestly; a
        provider that cannot retrieve the full list must say so rather than pad it.
        """

    @abstractmethod
    async def get_index_ohlc(self, index_name: str, interval: str = "3m") -> pd.DataFrame:
        """
        Daily OHLC level series for an NSE index (benchmark or sectoral).
        Default is "3m", NOT "6m" or "max" — get_index_history has no
        pagination and truncates its response at ~25,000 chars, and it
        drops the MOST RECENT bars while keeping old ones (verified twice:
        "max" on Nifty Auto returned 2004-2005 data instead of current, and
        "6m" on several large sectors — Nifty 50, Bank, IT, Auto, FMCG,
        Healthcare, Chemicals, Energy, Financial Services, Metal, Oil & Gas
        — claimed 127/current-to-date bars in its metadata but the actual
        bars array silently stopped ~6 weeks early). "3m" is small enough to
        reliably stay under the truncation limit for every sector observed
        so far, at the cost of not having enough history for weekly/monthly
        RSI — those are sourced from Angel One instead when available (see
        backend/sector_analysis/engine.py).
        """

    @abstractmethod
    async def get_stock_ohlcv(self, symbol: str, days: int = 500) -> pd.DataFrame:
        """Daily OHLCV for one stock."""

    @abstractmethod
    async def get_sector_performance(
        self, category: str | None = "sectoral", periods: int = 4, granularity: str = "week"
    ) -> list[dict[str, Any]]:
        """Official NSE index return ranking, for cross-checking locally computed sector returns."""

    @abstractmethod
    async def screen_technical(self, filters: list[dict[str, Any]], limit: int = 100) -> list[dict[str, Any]]:
        """Batch technical screener — the first-pass filter so we don't hit the API per-stock."""

    @abstractmethod
    async def get_batch_quotes(self, symbols: list[str]) -> list[dict[str, Any]]:
        """Live quotes for up to 20 symbols per call."""
