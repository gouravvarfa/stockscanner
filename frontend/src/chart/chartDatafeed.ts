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

  // Daily / weekly / monthly come first from the end-of-day files the site ships for the listed stocks (2026-11-23,
  // user: charts opened slowly through Render + Angel One); anything else, or a stock without a file, uses the API.
  if (timeframe === "1D" || timeframe === "1W" || timeframe === "1M") {
    const eodBars = await eodCandles(symbol, timeframe);
    if (eodBars && eodBars.length) {
      cache.set(key, { bars: eodBars, fetchedAt: Date.now() });
      return eodBars;
    }
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

type EodRow = [number, number, number, number, number, number];
const eodFiles = new Map<string, Promise<{ daily: EodRow[]; monthly: EodRow[] } | null>>();

function toBars(rows: EodRow[]): OHLCBar[] {
  return rows.map(([time, open, high, low, close, volume]) => ({ time, open, high, low, close, volume }));
}

/** Weekly candles (week starting Monday) from daily ones. */
function weekly(daily: OHLCBar[]): OHLCBar[] {
  const out: OHLCBar[] = [];
  for (const b of daily) {
    const d = new Date(b.time * 1000);
    const monday = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() - ((d.getUTCDay() + 6) % 7)) / 1000;
    const last = out[out.length - 1];
    if (last && last.time === monday) {
      last.high = Math.max(last.high, b.high);
      last.low = Math.min(last.low, b.low);
      last.close = b.close;
      last.volume = (last.volume ?? 0) + (b.volume ?? 0);
    } else {
      out.push({ time: monday, open: b.open, high: b.high, low: b.low, close: b.close, volume: b.volume });
    }
  }
  return out;
}

async function eodCandles(symbol: string, timeframe: Timeframe): Promise<OHLCBar[] | null> {
  let file = eodFiles.get(symbol);
  if (!file) {
    file = fetch(`/eod/candles/${encodeURIComponent(symbol)}.json?d=${new Date().toISOString().slice(0, 10)}`)
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null);
    eodFiles.set(symbol, file);
  }
  const data = await file;
  if (!data) return null;
  if (timeframe === "1M") return toBars(data.monthly);
  const daily = toBars(data.daily);
  return timeframe === "1W" ? weekly(daily) : daily;
}
