import { describe, expect, it } from "vitest";
import { isStale, lastClose } from "./WeeklyReportContext";

// IST = UTC+5:30; 15:30 IST = 10:00 UTC
describe("weekly report staleness", () => {
  it("last close on a weekday evening is today 15:30 IST", () => {
    expect(lastClose(new Date("2026-11-24T14:00:00Z")).toISOString()).toBe("2026-11-24T10:00:00.000Z");
  });
  it("before the close it is the previous trading day, skipping the weekend", () => {
    expect(lastClose(new Date("2026-11-23T05:00:00Z")).toISOString()).toBe("2026-11-20T10:00:00.000Z");
  });
  it("a report made after the last close is fresh outside market hours", () => {
    expect(isStale("2026-11-24T11:00:00Z", new Date("2026-11-24T16:00:00Z"))).toBe(false);
    expect(isStale("2026-11-24T09:00:00Z", new Date("2026-11-24T16:00:00Z"))).toBe(true);
  });
  it("during market hours a report over an hour old is stale", () => {
    expect(isStale("2026-11-25T04:00:00Z", new Date("2026-11-25T04:30:00Z"))).toBe(false);
    expect(isStale("2026-11-25T04:00:00Z", new Date("2026-11-25T05:30:00Z"))).toBe(true);
  });
  it("no report is stale", () => expect(isStale(undefined)).toBe(true));
});
