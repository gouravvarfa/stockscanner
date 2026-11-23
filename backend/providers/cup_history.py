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


# Token bucket (2026-11-23): every Cup history request takes a token; tokens refill at a steady rate shared by all the
# stocks running in parallel. Angel One allows about 3 historical-candle calls a second, so the bucket keeps the scan
# just under that however many stocks run at once - fast, but without tripping the limiter.
BUCKET_RATE_PER_SECOND = 2.5
BUCKET_CAPACITY = 3


class _TokenBucket:
    def __init__(self, rate: float, capacity: int):
        self.rate, self.capacity = rate, float(capacity)
        self.tokens = float(capacity)
        self.updated = 0.0
        self._lock: asyncio.Lock | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def take(self) -> None:
        loop = asyncio.get_running_loop()
        if self._lock is None or self._loop is not loop:  # a lock belongs to one event loop
            self._lock, self._loop = asyncio.Lock(), loop
            self.tokens, self.updated = self.capacity, 0.0
        async with self._lock:
            while True:
                now = loop.time()
                if self.updated == 0.0:
                    self.updated = now
                self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
                self.updated = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                await asyncio.sleep((1 - self.tokens) / self.rate)


_bucket = _TokenBucket(BUCKET_RATE_PER_SECOND, BUCKET_CAPACITY)


# Angel One's rate limiter answers HTTP 403 / "Too many requests" when calls bunch up. That is temporary, so a chunk
# is retried with a growing pause instead of failing the whole stock (2026-11-23: half of an all-NSE Cup scan was
# failing on exactly this and those stocks were silently missing from the results).
RATE_LIMIT_RETRIES = 4
RATE_LIMIT_BACKOFF_SECONDS = (4.0, 8.0, 15.0, 30.0)


def _is_rate_limited(exc: Exception) -> bool:
    text = str(exc).lower()
    return "403" in text or "too many requests" in text or "rate" in text and "limit" in text


async def _fetch_with_retry(angelone: AngelOneProvider, exch_seg: str, token: str, start: dt.datetime, end: dt.datetime) -> pd.DataFrame:
    for attempt in range(RATE_LIMIT_RETRIES + 1):
        try:
            await _bucket.take()
            return await angelone.get_daily_ohlc_range(exch_seg, token, start, end)
        except Exception as exc:  # noqa: BLE001 - only rate-limit errors are retried; anything else is raised as before
            if attempt >= RATE_LIMIT_RETRIES or not _is_rate_limited(exc):
                raise
            wait = RATE_LIMIT_BACKOFF_SECONDS[min(attempt, len(RATE_LIMIT_BACKOFF_SECONDS) - 1)]
            logger.info("Cup history: rate limited (%s), retry %d in %.0fs", exc, attempt + 1, wait)
            await asyncio.sleep(wait)
    raise RuntimeError("unreachable")


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
        df = await _fetch_with_retry(angelone, exch_seg, token, cur, chunk_end)
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

    When config.enable_disk_cache is False (Render, by default — see
    CupConfig docstring), both the read and the write below are skipped
    entirely: every call does a full chunked fetch and nothing is ever
    persisted to this instance's disk, so nothing can accumulate there
    across a scan or across restarts.
    """
    match = await angelone.resolve_equity(symbol)
    if match is None:
        raise CupDataUnavailableError(f"Angel One has no equity listing for '{symbol}'.")

    now = dt.datetime.now()
    entry = cup_disk_cache.load(symbol) if config.enable_disk_cache else None

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
            if config.enable_disk_cache:
                cup_disk_cache.save(symbol, merged)
            return merged
        # Cached depth no longer covers the requested history_years (e.g.
        # config was widened since this was cached) — safe invalidation:
        # fall through to a full refetch rather than serve a short window.

    start = now - dt.timedelta(days=int(config.history_years * 365.25))
    full = await _fetch_chunked(angelone, match.exch_seg, match.token, start, now, config)
    if config.enable_disk_cache:
        cup_disk_cache.save(symbol, full)
    return full
