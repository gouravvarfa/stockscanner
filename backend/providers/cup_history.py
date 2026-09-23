"""
Dedicated ~10-year daily-history fetcher + cache for the Cup Breakout
scanner ONLY. Completely separate from market_data_router.fetch_daily_ohlcv
(used by PRD/NRD/GFS/Value Buy, MONTHLY_RSI_LOOKBACK_DAYS/1500 days) — Cup
needs a much longer window and its own cache namespace so the two are never
confused or share a TTL/key.

Angel One's ONE_DAY candle endpoint was verified live and read-only
(2026-09-23) to reliably return ~2 years/request without truncating actual
history — BHEL data confirmed available back to at least 2005-01-03 — but
rapid back-to-back requests trip its rate limiter (HTTP 403), which clears
up entirely once requests are spaced a few seconds apart. Hence the
mandatory delay between chunks here.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging

import pandas as pd

from backend.config.cup_config import CupConfig
from backend.core.cache import cache
from backend.providers.angelone_provider import AngelOneProvider

logger = logging.getLogger("scanner.cup_history")

CACHE_KEY_PREFIX = "cup_history_daily"
CACHE_TTL_SECONDS = 24 * 3600  # a fresh chunk-refresh once/day is enough for a monthly-timeframe strategy


class CupDataUnavailableError(RuntimeError):
    pass


def _cache_key(symbol: str) -> str:
    return f"{CACHE_KEY_PREFIX}:{symbol}"


def _dedupe_and_sort(frames: list[pd.DataFrame]) -> pd.DataFrame:
    non_empty = [f for f in frames if not f.empty]
    if not non_empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    combined = pd.concat(non_empty)
    combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    return combined


async def _fetch_chunked(
    angelone: AngelOneProvider, exch_seg: str, token: str, start: dt.datetime, end: dt.datetime, config: CupConfig,
) -> pd.DataFrame:
    """Splits [start, end) into config.chunk_years-sized windows, fetching
    oldest-first with a delay between requests to stay under Angel One's
    rate limiter (see module docstring)."""
    frames: list[pd.DataFrame] = []
    cur = start
    first = True
    while cur < end:
        chunk_end = min(cur + dt.timedelta(days=int(config.chunk_years * 365.25)), end)
        if not first:
            await asyncio.sleep(config.chunk_delay_seconds)
        first = False
        df = await angelone.get_daily_ohlc_range(exch_seg, token, cur, chunk_end)
        frames.append(df)
        cur = chunk_end
    return _dedupe_and_sort(frames)


async def fetch_cup_history(angelone: AngelOneProvider, symbol: str, config: CupConfig) -> pd.DataFrame:
    """
    Returns ~config.history_years of daily OHLCV for `symbol`, using a
    dedicated in-process cache (see module docstring): a cold cache does the
    full chunked multi-year fetch once; a warm-but-stale cache only fetches
    the missing tail (today back to the cache's last known date) and merges
    it in — "don't download the complete N years again unnecessarily", per
    spec. Cache is in-process only (cleared on a Render restart, same as
    every other in-process cache in this project) — acceptable since a cold
    start just re-runs the full (slower) fetch once.
    """
    match = await angelone.resolve_equity(symbol)
    if match is None:
        raise CupDataUnavailableError(f"Angel One has no equity listing for '{symbol}'.")

    now = dt.datetime.now()
    key = _cache_key(symbol)
    cached: pd.DataFrame | None = cache.get(key)

    if cached is not None and not cached.empty:
        last_cached_date = cached.index.max()
        if (now - last_cached_date).days <= 1:
            return cached  # already fresh (fetched earlier today) — no network call at all
        # Only fetch the missing tail, not the full N years again.
        fresh_tail = await _fetch_chunked(angelone, match.exch_seg, match.token, last_cached_date, now, config)
        merged = _dedupe_and_sort([cached, fresh_tail])
        cache.set(key, merged, CACHE_TTL_SECONDS)
        return merged

    start = now - dt.timedelta(days=int(config.history_years * 365.25))
    full = await _fetch_chunked(angelone, match.exch_seg, match.token, start, now, config)
    cache.set(key, full, CACHE_TTL_SECONDS)
    return full
