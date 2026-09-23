import { api } from "../services/api";
import type { OHLCBar, Timeframe } from "./chartTypes";

/** symbol+timeframe -> bars, so switching back to an already-viewed timeframe this session is instant and never re-fetches. */
const cache = new Map<string, OHLCBar[]>();

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
  if (cached) {
    return cached;
  }

  const res = await api.getChartCandles(symbol, timeframe, signal, longHistory);
  const bars = res.candles;
  cache.set(key, bars);
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
