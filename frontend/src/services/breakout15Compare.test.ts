import { describe, expect, it } from "vitest";
import { exportFileName, type Breakout15Row, type ManualRow } from "./breakout15Api";
import { compareToCsv, compareWithManual, summarizeComparison } from "./breakout15Compare";

const bt = (date: string, over: Partial<Breakout15Row>): Breakout15Row => ({
  date, first_open: 100, first_high: 101, first_low: 99, first_close: 100, first_range_pct: 0.3, first_direction: "Green",
  side: null, breakout_time: null, entry_price: null, stop_loss: 99, second_last_time: null, second_last_close: null, second_last_change_pct: null,
  exit_time: null, exit_price: null, exit_reason: "NO_ENTRY", pnl_points: null, pnl_pct: null, flags: [], quality: "OK", ...over,
});
const man = (date: string, over: Partial<ManualRow>): ManualRow => ({ date, side: "CALL", candle_pct: 0.31, outcome: "LOSS", eod_pct: 0.3, ...over });

describe("compareWithManual", () => {
  it("matches a CALL result by profit/loss", () => {
    const [r] = compareWithManual([man("2025-01-07", {})], [bt("2025-01-07", { side: "CALL", exit_reason: "STOP_LOSS", pnl_points: -96, pnl_pct: -0.4 })]);
    expect(r.verdict).toBe("MATCH");
    expect(r.candleDiff).toBeCloseTo(-0.01);
  });
  it("flags a result disagreement", () => {
    const [r] = compareWithManual([man("2025-01-07", { outcome: "PROFIT" })], [bt("2025-01-07", { side: "CALL", exit_reason: "STOP_LOSS", pnl_points: -5 })]);
    expect(r.verdict).toBe("DIFFERENT");
  });
  it("compares PUT days too, and flags a side disagreement even when both lost", () => {
    const rows = compareWithManual(
      [man("2025-01-01", { side: "PUT", outcome: "LOSS" }), man("2025-01-02", { side: "PUT", outcome: "LOSS" })],
      [bt("2025-01-01", { side: "PUT", exit_reason: "STOP_LOSS", pnl_points: -77 }), bt("2025-01-02", { side: "CALL", exit_reason: "STOP_LOSS", pnl_points: -50 })],
    );
    expect(rows.map((r) => r.verdict)).toEqual(["MATCH", "DIFFERENT"]);
  });
  it("treats a both-ends ambiguous stop as matching a LOSS row on either side, and marks dates without data", () => {
    const rows = compareWithManual(
      [man("2025-01-02", { side: "PUT", outcome: "LOSS" }), man("2025-01-11", {})],
      [bt("2025-01-02", { side: "BOTH", exit_reason: "STOP_LOSS", pnl_points: -20 })],
    );
    expect(rows.map((r) => r.verdict)).toEqual(["MATCH", "NO_DATA"]);
    expect(rows[1].backtestOutcome).toBeNull();
  });
  it("summarizes", () => {
    const rows = compareWithManual(
      [man("2025-01-07", {}), man("2025-01-08", { outcome: "PROFIT" })],
      [bt("2025-01-07", { side: "CALL", exit_reason: "STOP_LOSS", pnl_points: -1 }), bt("2025-01-08", { side: "CALL", exit_reason: "STOP_LOSS", pnl_points: -1 })],
    );
    expect(summarizeComparison(rows)).toMatchObject({ compared: 2, callRows: 2, callMatches: 1, noData: 0 });
  });
});

describe("compareToCsv", () => {
  it("writes a header, one line per row, and quotes awkward cells", () => {
    const rows = compareWithManual([man("2025-01-07", {})], [bt("2025-01-07", { side: "CALL", exit_reason: "STOP_LOSS", pnl_points: -96, pnl_pct: -0.41 })]);
    const lines = compareToCsv(rows).replace("﻿", "").split("\n");
    expect(lines).toHaveLength(2);
    expect(lines[0].startsWith("Date,Excel side")).toBe(true);
    expect(lines[1]).toBe("2025-01-07,CALL,CALL,0.31,0.3,-0.01,LOSS,LOSS,0.3,-0.41,MATCH");
  });
});

describe("exportFileName", () => {
  it("carries the index and the exact date range so different ranges never share a name", () => {
    expect(exportFileName({ symbol: "NIFTY", from: "2025-01-01", to: "2025-01-24", exit_mode: "CLOSE" })).toBe("NIFTY_2025-01-01_to_2025-01-24.xlsx");
    expect(exportFileName({ symbol: "BANKNIFTY", from: "2025-02-03", to: "2025-03-28", exit_mode: "SECOND_LAST" })).toBe("BANKNIFTY_2025-02-03_to_2025-03-28_exit-1515.xlsx");
  });
});
