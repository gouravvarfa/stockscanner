import { describe, expect, it } from "vitest";
import { mapPartialSignalsToRows, mapProgressItemToRow, mapScanResultToHistoryRows } from "./historyRowMapping";
import type { ScanResult } from "./api";
import type { PartialResult } from "./scanJobsApi";

describe("historyRowMapping", () => {
  it("preserves FUTURE/EQUITY classification and PRD_FORMING detail from the live partial stream", () => {
    const partial: PartialResult = {
      seq: 1,
      symbol: "NILKAMAL",
      instrument_type: "EQUITY",
      strategies: ["PRD Forming"],
      signals: [
        {
          strategy: "PRD Forming",
          symbol: "NILKAMAL",
          instrument_type: "EQUITY",
          qualifies: false,
          daily_rsi: 43.2,
          weekly_rsi: 64.04,
          monthly_rsi: 61.2,
          explanation: "developing",
          extra: {
            current_price: 1887.5,
            forming: [
              {
                timeframe: "weekly",
                a_date: "2026-08-07 00:00:00",
                a_low: 1640.0,
                a_rsi: 73.02,
                b_date: "2026-09-18 00:00:00",
                b_low: 1844.2,
                b_rsi: 64.04,
                ab_distance: 6,
              },
            ],
          },
        },
      ],
    };
    const rows = mapPartialSignalsToRows("a_group:job:scan_1", partial);
    expect(rows).toHaveLength(1);
    expect(rows[0].instrumentType).toBe("EQUITY");
    expect(rows[0].status).toBe("PRD_FORMING");
    expect(rows[0].timeframe).toBe("WEEKLY");
    expect(rows[0].aDate).toBe("2026-08-07");
    expect(rows[0].bDate).toBe("2026-09-18");
    expect(rows[0].aRsi).toBe(73.02);
    expect(rows[0].bRsi).toBe(64.04);
    expect(rows[0].abDistance).toBe(6);
  });

  it("preserves PRD_CONFIRMED detail from the final result", () => {
    const result = {
      scan_id: 1,
      nifty200_universe: [{ symbol: "RELIANCE", instrument_type: "FUTURE", status: "OK" }],
      strategies: {
        PRD: [
          {
            strategy: "PRD",
            symbol: "RELIANCE",
            instrument_type: "FUTURE",
            qualifies: true,
            daily_rsi: 62,
            weekly_rsi: 70,
            monthly_rsi: 68,
            explanation: "PRD CONFIRMED",
            extra: {
              current_price: 2900,
              status: "PRD_CONFIRMED",
              divergences: [
                { timeframe: "weekly", a_date: "2026-08-01", b_date: "2026-09-18", a_low: 2500, b_low: 2900, a_rsi: 75, b_rsi: 70, ab_distance: 7 },
              ],
            },
          },
        ],
      },
    } as unknown as ScanResult;
    const rows = mapScanResultToHistoryRows("a_group:job:scan_1", result);
    expect(rows).toHaveLength(1);
    expect(rows[0].status).toBe("PRD_CONFIRMED");
    expect(rows[0].instrumentType).toBe("FUTURE");
    expect(rows[0].aPrice).toBe(2500);
    expect(rows[0].bPrice).toBe(2900);
  });

  it("marks a failed stock as DATA_UNAVAILABLE and a scanned-clean stock as SCANNED_NO_SIGNAL", () => {
    const failed = mapProgressItemToRow("a_group:job:scan_1", {
      seq: 1, symbol: "BADSTOCK", instrument_type: "EQUITY", success: false, error: "timeout",
    });
    expect(failed.status).toBe("DATA_UNAVAILABLE");
    expect(failed.details).toBe("timeout");

    const clean = mapProgressItemToRow("a_group:job:scan_1", {
      seq: 2, symbol: "GOODSTOCK", instrument_type: "FUTURE", success: true, error: null,
    });
    expect(clean.status).toBe("SCANNED_NO_SIGNAL");
    expect(clean.instrumentType).toBe("FUTURE");
  });

  it("produces the same deterministic id for the same (symbol, strategy, timeframe, A date) every time", () => {
    const partial: PartialResult = {
      seq: 1,
      symbol: "TCS",
      instrument_type: "FUTURE",
      strategies: ["GFS"],
      signals: [
        {
          strategy: "GFS", symbol: "TCS", instrument_type: "FUTURE", qualifies: true,
          daily_rsi: 60, weekly_rsi: 65, monthly_rsi: 62, explanation: "x", extra: { current_price: 3900 },
        },
      ],
    };
    const rows1 = mapPartialSignalsToRows("a_group:job:scan_1", partial);
    const rows2 = mapPartialSignalsToRows("a_group:job:scan_1", partial);
    expect(rows1[0].id).toBe(rows2[0].id); // same key both times -> IndexedDB put() upserts, never duplicates
  });

  it("collapses multiple PRD/NRD Forming candidates on the same timeframe to the single freshest one (2026-09-28 duplicate-rows report)", () => {
    const partial: PartialResult = {
      seq: 1,
      symbol: "AEGISLOG",
      instrument_type: "EQUITY",
      strategies: ["PRD Forming"],
      signals: [
        {
          strategy: "PRD Forming",
          symbol: "AEGISLOG",
          instrument_type: "EQUITY",
          qualifies: false,
          daily_rsi: 60, weekly_rsi: 63.6, monthly_rsi: 61,
          explanation: "developing",
          extra: {
            current_price: 1309.7,
            // Same B candle, three different valid A pivots — exactly what
            // the backend's _developing_structures legitimately returns.
            forming: [
              { timeframe: "weekly", a_date: "2026-07-17", a_low: 1200, a_rsi: 70, b_date: "2026-09-25", b_low: 1309.7, b_rsi: 63.6, ab_distance: 10 },
              { timeframe: "weekly", a_date: "2026-07-31", a_low: 1210, a_rsi: 68, b_date: "2026-09-25", b_low: 1309.7, b_rsi: 63.6, ab_distance: 8 },
              { timeframe: "weekly", a_date: "2026-08-14", a_low: 1220, a_rsi: 66, b_date: "2026-09-25", b_low: 1309.7, b_rsi: 63.6, ab_distance: 6 },
            ],
          },
        },
      ],
    };
    const rows = mapPartialSignalsToRows("a_group:job:scan_1", partial);
    expect(rows).toHaveLength(1); // not 3
    expect(rows[0].abDistance).toBe(6); // the freshest (smallest A-B distance) candidate wins
    expect(rows[0].aDate).toBe("2026-08-14");
  });

  it("keeps one row PER timeframe when Forming candidates span multiple timeframes", () => {
    const partial: PartialResult = {
      seq: 1,
      symbol: "AHLUCONT",
      instrument_type: "EQUITY",
      strategies: ["NRD Forming"],
      signals: [
        {
          strategy: "NRD Forming",
          symbol: "AHLUCONT",
          instrument_type: "EQUITY",
          qualifies: false,
          daily_rsi: 27.8, weekly_rsi: 30, monthly_rsi: 35,
          explanation: "developing",
          extra: {
            current_price: 567.1,
            forming: [
              { timeframe: "daily", a_date: "2026-09-04", a_low: 600, a_rsi: 40, b_date: "2026-09-28", b_low: 567.1, b_rsi: 27.8, ab_distance: 15 },
              { timeframe: "daily", a_date: "2026-09-09", a_low: 590, a_rsi: 38, b_date: "2026-09-28", b_low: 567.1, b_rsi: 27.8, ab_distance: 12 },
              { timeframe: "weekly", a_date: "2026-07-01", a_low: 620, a_rsi: 45, b_date: "2026-09-25", b_low: 570, b_rsi: 30, ab_distance: 9 },
            ],
          },
        },
      ],
    };
    const rows = mapPartialSignalsToRows("a_group:job:scan_1", partial);
    expect(rows).toHaveLength(2); // one daily + one weekly, not three
    const daily = rows.find((r) => r.timeframe === "DAILY");
    expect(daily?.abDistance).toBe(12); // freshest of the two daily candidates
    const weekly = rows.find((r) => r.timeframe === "WEEKLY");
    expect(weekly?.abDistance).toBe(9);
  });
});
