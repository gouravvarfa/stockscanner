from __future__ import annotations

import hashlib
import json
from typing import Any

import pandas as pd

from backend.core.cache import (
    TTL_DAILY_OHLCV,
    TTL_INDEX_HISTORY,
    TTL_LIVE_QUOTE,
    TTL_SECTOR_PERFORMANCE,
    TTL_UNIVERSE,
    cache,
)
from backend.providers import call_metrics
from backend.providers.base import MarketDataProvider
from backend.providers.tapetide_client import TapetideMCPClient


def _bars_to_frame(bars: list[dict[str, Any]]) -> pd.DataFrame:
    if not bars:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.DataFrame(bars)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    if "volume" not in df.columns:
        df["volume"] = 0.0
    return df[["open", "high", "low", "close", "volume"]].astype(float)


class TapetideProvider(MarketDataProvider):
    """
    Normalizes Tapetide's real MCP tool responses (verified shapes — see
    backend/providers/tapetide_client.py header) into the plain
    dict/DataFrame contracts the rest of the scanner expects.
    """

    def __init__(self, client: TapetideMCPClient) -> None:
        self._client = client

    async def _cached_call(self, tool_name: str, arguments: dict[str, Any], ttl_seconds: int) -> Any:
        """
        Caches Tapetide tool responses locally. This matters beyond mere speed:
        Tapetide's free tier caps requests at 50 MCP calls/day (hit during
        development — see backend/README notes), so avoiding a repeat call for
        data that hasn't gone stale is what keeps re-scans within quota.
        """
        key_raw = tool_name + "|" + json.dumps(arguments, sort_keys=True, default=str)
        key = "tapetide:" + hashlib.sha256(key_raw.encode()).hexdigest()

        cached = cache.get(key)
        if cached is not None:
            call_metrics.record_tapetide_cache_hit()
            return cached

        call_metrics.record_tapetide_cache_miss()
        call_metrics.record_tapetide_call()
        result = await self._client.call(tool_name, arguments)
        cache.set(key, result, ttl_seconds)
        return result

    # market_heatmap truncates its response around ~25,000 characters server-side
    # (confirmed empirically — even a single call for "nifty-50" alone comes back
    # truncated), with no pagination/offset parameter exposed. A single call for
    # "nifty-200" therefore returns roughly the first 33 of 200 constituents. To
    # get honest, real (not fabricated) coverage of the universe we combine the
    # nifty-200 call with the large-cap building blocks and every sectoral slug
    # small enough to return in full, and de-duplicate by symbol. Coverage is
    # reported explicitly rather than silently padded — see get_universe.
    _SECTORAL_SLUGS = (
        "nifty-bank", "nifty-it", "nifty-pharma", "nifty-auto", "nifty-fmcg",
        "nifty-metal", "nifty-energy", "nifty-realty", "nifty-infra", "nifty-psu-bank",
    )

    async def _heatmap(self, index_slug: str) -> tuple[list[dict[str, Any]], int]:
        response = await self._cached_call("market_heatmap", {"index": index_slug}, TTL_UNIVERSE)
        return response.get("data", []), response.get("tot_rec", 0)

    async def get_universe(self, index_slug: str = "nifty-200") -> dict[str, Any]:
        target_rows, requested = await self._heatmap(index_slug)
        by_symbol: dict[str, dict[str, Any]] = {}
        sources_used = [index_slug]

        def ingest(rows: list[dict[str, Any]]) -> None:
            for row in rows:
                sym = row.get("Sym")
                if sym and sym not in by_symbol:
                    by_symbol[sym] = {
                        "symbol": sym,
                        "sector": row.get("Sector"),
                        "exchange": row.get("Exch"),
                        "isin": row.get("Isin"),
                        "market_cap_cr": row.get("Mcap"),
                    }

        ingest(target_rows)

        if len(by_symbol) < requested:
            for slug in ("nifty-50", "nifty-next-50", *self._SECTORAL_SLUGS):
                if len(by_symbol) >= requested:
                    break
                rows, _ = await self._heatmap(slug)
                ingest(rows)
                sources_used.append(slug)

        # Only keep symbols that are actually members of the requested index
        # (the sectoral/large-cap fill-in calls can include names outside it,
        # e.g. NIFTY 500-only stocks in a sectoral index).
        target_symbols = {row.get("Sym") for row in target_rows if row.get("Sym")}
        if index_slug == "nifty-200" and len(target_symbols) < requested:
            # target_rows alone under-covers nifty-200's own symbol set (same
            # truncation problem), so we cannot filter fill-ins by it here —
            # report the union as best-effort coverage instead of dropping data.
            stocks = list(by_symbol.values())
        else:
            stocks = [v for k, v in by_symbol.items() if k in target_symbols] or list(by_symbol.values())

        note = None
        if index_slug == "nifty-200" and len(target_symbols) < requested:
            note = (
                "market_heatmap truncates before returning all 200 constituents and "
                "exposes no pagination parameter. Coverage was extended using the "
                "nifty-50/nifty-next-50 and sectoral index heatmaps, de-duplicated by "
                "symbol; a small number of these fill-in names may belong to a broader "
                "index (e.g. Nifty 500) rather than strictly Nifty 200. Treat 'complete' "
                "as best-effort, not exchange-verified, membership."
            )

        return {
            "stocks": stocks,
            "requested": requested,
            "returned": len(stocks),
            "complete": len(stocks) >= requested > 0,
            "sources": sources_used,
            "note": note,
        }

    async def get_index_ohlc(self, index_name: str, interval: str = "6m") -> pd.DataFrame:
        response = await self._cached_call(
            "get_index_history", {"index_name": index_name, "interval": interval}, TTL_INDEX_HISTORY
        )
        bars = response.get("data", {}).get("bars", [])
        return _bars_to_frame(bars)

    async def get_stock_ohlcv(self, symbol: str, days: int = 500) -> pd.DataFrame:
        all_bars: list[dict[str, Any]] = []
        end_date: str | None = None
        remaining = days

        while remaining > 0:
            request_days = min(remaining, 2000)
            args: dict[str, Any] = {"symbol": symbol, "days": request_days, "interval": "daily"}
            if end_date:
                args["end_date"] = end_date
            response = await self._cached_call("get_price_history", args, TTL_DAILY_OHLCV)
            bars = response.get("data", [])
            all_bars.extend(bars)

            window = response.get("meta", {}).get("window", {})
            if not window.get("truncated") or not window.get("next_cursor"):
                break
            end_date = window["next_cursor"]
            remaining -= len(bars) or request_days

        return _bars_to_frame(all_bars)

    async def get_sector_performance(
        self, category: str | None = "sectoral", periods: int = 4, granularity: str = "week"
    ) -> list[dict[str, Any]]:
        args: dict[str, Any] = {"periods": periods, "granularity": granularity, "limit": 50}
        if category:
            args["category"] = category
        response = await self._cached_call("get_index_performance", args, TTL_SECTOR_PERFORMANCE)
        return response.get("data", {}).get("indices", [])

    async def screen_technical(self, filters: list[dict[str, Any]], limit: int = 100) -> list[dict[str, Any]]:
        response = await self._cached_call(
            "screen_stocks_technical", {"filters": filters, "limit": limit}, TTL_LIVE_QUOTE
        )
        return response.get("data", response) if isinstance(response, dict) else response

    async def get_batch_quotes(self, symbols: list[str]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for i in range(0, len(symbols), 20):
            chunk = symbols[i : i + 20]
            response = await self._cached_call("get_batch_quotes", {"symbols": chunk}, TTL_LIVE_QUOTE)
            data = response.get("data", response) if isinstance(response, dict) else response
            results.extend(data if isinstance(data, list) else [])
        return results
