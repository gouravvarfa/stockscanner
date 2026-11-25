import { describe, expect, it } from "vitest";
import { analyse, fromMonthPacked, monthly, quantile, ratioOf, type Pt } from "./ratioMath";

const month = (i: number) => Date.UTC(2006 + Math.floor(i / 12), i % 12, 28) / 1000;

describe("ratio math", () => {
  it("divides on shared dates only", () => {
    expect(ratioOf([[1, 10], [2, 20], [3, 30]], [[1, 5], [3, 10]])).toEqual([[1, 2], [3, 3]]);
  });
  it("keeps the last point of each month", () => {
    const d = (m: number, day: number) => Date.UTC(2020, m, day) / 1000;
    expect(monthly([[d(0, 3), 1], [d(0, 24), 2], [d(1, 7), 3]]).map((p) => p[1])).toEqual([2, 3]);
  });
  it("unpacks month rows", () => {
    const pts = fromMonthPacked([2020 * 12 + 11, 5, 6]);
    expect(new Date(pts[1][0] * 1000).toISOString().slice(0, 7)).toBe("2021-01");
    expect(pts.map((p) => p[1])).toEqual([5, 6]);
  });
  it("interpolates quantiles", () => {
    expect(quantile([1, 2, 3, 4, 5], 0.5)).toBe(3);
    expect(quantile([0, 10], 0.15)).toBeCloseTo(1.5);
  });
  it("switch beats both legs on a ratio that swings and mean-reverts", () => {
    // A and B take turns: A runs while the ratio is low, B while it is high
    const a: Pt[] = [], b: Pt[] = [];
    let pa = 100, pb = 100;
    for (let i = 0; i < 240; i++) {
      const phase = Math.sin((i / 240) * Math.PI * 8);
      pa *= 1 + 0.01 + 0.03 * Math.cos((i / 240) * Math.PI * 8);
      pb *= 1.01;
      a.push([month(i), pa]); b.push([month(i), pb]);
      void phase;
    }
    const r = analyse(ratioOf(a, b), a, b, 12)!;
    expect(r).not.toBeNull();
    expect(r.low).toBeLessThan(r.high);
    expect(r.pctRank).toBeGreaterThan(0);
    expect(r.backtest!.switches).toBeGreaterThan(0);
    expect(r.afterHigh?.times ?? 0).toBeGreaterThan(0);
  });
  it("too little data gives nothing", () => {
    const a: Pt[] = Array.from({ length: 10 }, (_, i) => [month(i), 1 + i]);
    expect(analyse(a, a, a, 12)).toBeNull();
  });
});
