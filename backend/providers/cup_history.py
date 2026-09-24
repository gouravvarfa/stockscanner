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
from backend.providers import cup_disk_cache
from backend.providers.angelone_provider import AngelOneProvider

logger = logging.getLogger("scanner.cup_history")

CACHE_TTL_HOURS = 24  # a fresh chunk-refresh once/day is enough for a monthly-timeframe strategy


class CupDataUnavailableError(RuntimeError):
    pass


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
    Returns ~config.history_years of daily OHLCV for `symbol`, using the
    isolated per-symbol on-disk cache (backend/providers/cup_disk_cache.py —
    see its module docstring for why this is NOT the shared FileCache): a
    cold cache does the full chunked multi-year fetch once; a warm-but-
    stale cache only fetches the missing tail (today back to the cache's
    last known date) and merges it in — "don't download the complete N
    years again unnecessarily", per spec. A cache whose depth no longer
    covers config.history_years (e.g. history_years was increased since it
    was written) is treated as a miss and fully refetched, rather than
    silently served an insufficient window.

    Only THIS symbol's DataFrame is ever loaded into memory here — the
    caller (cup_scan_service.py) lets it go out of scope once this stock's
    Cup detection finishes, so nothing accumulates across a scan.
    """
    match = await angelone.resolve_equity(symbol)
    if match is None:
        raise CupDataUnavailableError(f"Angel One has no equity listing for '{symbol}'.")

    now = dt.datetime.now()
    entry = cup_disk_cache.load(symbol)

    if entry is not None:
        # +10 day tolerance: the oldest cached bar is a real trading day
        # (weekends/holidays shift it a few days from the exact calendar
        # cutoff), so an exact `<=` would spuriously force a full refetch.
        required_start = now - dt.timedelta(days=int(config.history_years * 365.25))
        if entry.oldest_date is not None and entry.oldest_date <= required_start + dt.timedelta(days=10):
            if (now - entry.newest_date).days <= 1:
                return entry.data  # already fresh (fetched earlier today) — no network call at all
            # Only fetch the missing tail, not the full N years again.
            fresh_tail = await _fetch_chunked(angelone, match.exch_seg, match.token, entry.newest_date, now, config)
            merged = _dedupe_and_sort([entry.data, fresh_tail])
            cup_disk_cache.save(symbol, merged)
            return merged
        # Cached depth no longer covers the requested history_years (e.g.
        # config was widened since this was cached) — safe invalidation:
        # fall through to a full refetch rather than serve a short window.

    start = now - dt.timedelta(days=int(config.history_years * 365.25))
    full = await _fetch_chunked(angelone, match.exch_seg, match.token, start, now, config)
    cup_disk_cache.save(symbol, full)
    return full
