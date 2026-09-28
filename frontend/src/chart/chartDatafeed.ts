import { api } from "../services/api";
import type { OHLCBar, Timeframe } from "./chartTypes";

/**
 * symbol+timeframe -> bars, so switching back to an already-viewed
 * timeframe this session is instant instead of re-fetching every time.
 *
 * Bounded TTL (2026-09-28, ACC bug): 1D/1W/1M (and any live-updating
 * intraday timeframe) now show the CURRENT still-forming candle — a cache
 * entry with no expiry froze that chart at whatever it looked like the
 * first time it was opened this session, silently going further and
 * further out of date (missing every trading day since) even though the
 * backend itself was already returning fresh data on every request. A
 * short TTL keeps the "instant re-open" win for rapid tab/timeframe
 * switching while guaranteeing the chart re-fetches real data at least
 * this often.
 */
const CACHE_TTL_MS = 30_000;

interface CacheEntry {
  bars: OHLCBar[];
  fetchedAt: number;
}

const cache = new Map<string, CacheEntry>();

function cacheKey(symbol: string, timeframe: Timeframe): string {
  return `${symbol}:${timeframe}`;
}

/**
 * Fetches candles for exactly one symbol+timeframe from our own FastAPI
 * chart endpoint (never TradingView, never a second market-data system).
 * Guards against out-of-order responses when the caller fires a new
 * request (symbol/timeframe change) before a prior one resolves — the
 * caller is responsible for passing a fresh AbortController per request.
 */
export async function fetchCandles(
  symbol: string,
  timeframe: Timeframe,
  signal?: AbortSignal,
  longHistory = false,
): Promise<OHLCBar[]> {
  // A separate cache key for the long-history variant — the normal
  // (short-window) and Cup's long-window candles for the same
  // symbol+timeframe are genuinely different data, never interchangeable.
  const key = longHistory ? `${cacheKey(symbol, timeframe)}:long` : cacheKey(symbol, timeframe);
  const cached = cache.get(key);
  if (cached && Date.now() - cached.fetchedAt < CACHE_TTL_MS) {
    return cached.bars;
  }

  const res = await api.getChartCandles(symbol, timeframe, signal, longHistory);
  const bars = res.candles;
  cache.set(key, { bars, fetchedAt: Date.now() });
  return bars;
}

export function clearChartCache(symbol?: string): void {
  if (!symbol) {
    cache.clear();
    return;
  }
  for (const key of Array.from(cache.keys())) {
    if (key.startsWith(`${symbol}:`)) {
      cache.delete(key);
    }
  }
}
