import { describe, expect, it } from "vitest";
import type { OHLCBar } from "./chartTypes";
import { snapToBar } from "./useTradingViewChart";

// Bars exactly as GET /api/chart/candles returns them: `time` is
// int(idx.timestamp()) of the backend's tz-naive index, i.e. UTC midnight
// of the bar's date. For 1M that date is the month END (resample "ME").
const utc = (y: number, m: number, d: number) => Date.UTC(y, m - 1, d) / 1000;
const bar = (time: number, high: number, low: number): OHLCBar => ({ time, open: low, high, low, close: high });

describe("Cup structure markers snap to the backend-reported bars", () => {
  const monthly: OHLCBar[] = [
    bar(utc(2021, 11, 30), 800, 700),
    bar(utc(2021, 12, 31), 839.9, 760), // backend left rim: 2021-12-31, 839.9
    bar(utc(2022, 1, 31), 820, 690),
    bar(utc(2025, 4, 30), 450, 380), // backend cup bottom: 2025-04-30, 380
    bar(utc(2026, 8, 31), 830, 780), // backend right rim: 2026-08-31
  ];

  it("places the left rim on the exact monthly bar the detector used", () => {
    expect(snapToBar(monthly, "2021-12-31T00:00:00", null, "high")).toBe(utc(2021, 12, 31));
  });

  it("places the cup bottom on the exact monthly bar the detector used", () => {
    expect(snapToBar(monthly, "2025-04-30T00:00:00", null, "low")).toBe(utc(2025, 4, 30));
  });

  it("places the right rim on the exact monthly bar the detector used", () => {
    expect(snapToBar(monthly, "2026-08-31T00:00:00", null, "high")).toBe(utc(2026, 8, 31));
  });

  it("on a daily chart, picks the real day of that month's extreme", () => {
    const daily: OHLCBar[] = [
      bar(utc(2021, 12, 1), 810, 790),
      bar(utc(2021, 12, 14), 839.9, 800), // the actual rim day
      bar(utc(2021, 12, 31), 820, 805),
      bar(utc(2022, 1, 3), 850, 810), // next month - must not be picked even though higher
    ];
    expect(snapToBar(daily, "2021-12-31T00:00:00", null, "high")).toBe(utc(2021, 12, 14));
    expect(snapToBar(daily, "2021-12-31T00:00:00", null, "low")).toBe(utc(2021, 12, 1));
    expect(snapToBar(daily, "2021-12-31T00:00:00", null, "last")).toBe(utc(2021, 12, 31));
  });

  it("marks a multi-month handle at its lowest bar across the whole range", () => {
    expect(snapToBar(monthly, "2021-11-30T00:00:00", "2022-01-31T00:00:00", "low")).toBe(utc(2022, 1, 31));
  });

  it("returns null (no marker) for missing dates or dates outside the loaded history", () => {
    expect(snapToBar(monthly, null, null, "high")).toBeNull();
    expect(snapToBar(monthly, "2010-06-30T00:00:00", null, "high")).toBeNull();
  });
});
