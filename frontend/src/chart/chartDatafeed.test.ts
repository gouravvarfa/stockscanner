import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../services/api", () => ({
  api: { getChartCandles: vi.fn() },
}));

import { api } from "../services/api";
import { clearChartCache, fetchCandles } from "./chartDatafeed";

const getChartCandles = api.getChartCandles as unknown as ReturnType<typeof vi.fn>;

function bar(close: number) {
  return { time: 1, open: close, high: close, low: close, close, volume: 1 };
}

beforeEach(() => {
  vi.useFakeTimers();
  clearChartCache();
  getChartCandles.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("chartDatafeed caching", () => {
  it("serves a repeat request within the TTL from cache, not the network", async () => {
    getChartCandles.mockResolvedValueOnce({ candles: [bar(100)] });
    await fetchCandles("ACC", "1D");
    await fetchCandles("ACC", "1D");
    expect(getChartCandles).toHaveBeenCalledTimes(1);
  });

  it("re-fetches once the TTL expires (regression: ACC's 1D chart froze on the first fetch of the session, hiding every later trading day)", async () => {
    getChartCandles.mockResolvedValueOnce({ candles: [bar(100)] }).mockResolvedValueOnce({ candles: [bar(101)] });
    const first = await fetchCandles("ACC", "1D");
    vi.advanceTimersByTime(31_000);
    const second = await fetchCandles("ACC", "1D");
    expect(getChartCandles).toHaveBeenCalledTimes(2);
    expect(first[0].close).toBe(100);
    expect(second[0].close).toBe(101);
  });

  it("keeps the long-history (Cup) variant in a separate cache key from the normal one", async () => {
    getChartCandles.mockResolvedValueOnce({ candles: [bar(1)] }).mockResolvedValueOnce({ candles: [bar(2)] });
    await fetchCandles("ACC", "1D", undefined, false);
    await fetchCandles("ACC", "1D", undefined, true);
    expect(getChartCandles).toHaveBeenCalledTimes(2);
  });

  it("clearChartCache forces the next fetch for that symbol to hit the network", async () => {
    getChartCandles.mockResolvedValue({ candles: [bar(1)] });
    await fetchCandles("ACC", "1D");
    clearChartCache("ACC");
    await fetchCandles("ACC", "1D");
    expect(getChartCandles).toHaveBeenCalledTimes(2);
  });
});
