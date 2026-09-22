import "fake-indexeddb/auto";
import { beforeEach, describe, expect, it } from "vitest";
import {
  clearAllHistory,
  getResultsForSnapshot,
  getSnapshot,
  listSnapshots,
  putResults,
  putSnapshot,
  resultRowKey,
  storageStats,
  type HistoryResultRow,
  type HistorySnapshotMeta,
} from "./localHistoryDb";

function meta(overrides: Partial<HistorySnapshotMeta> = {}): HistorySnapshotMeta {
  return {
    localId: "a_group:job:scan_1",
    scanId: null,
    jobId: "scan_1",
    scanType: "a_group",
    scanDate: "2026-09-22",
    scanTime: "11:35:00",
    startedAt: "2026-09-22T06:05:00.000Z",
    completedAt: null,
    durationSeconds: null,
    totalStocks: 615,
    processedStocks: 0,
    successfulStocks: 0,
    failedStocks: 0,
    signalCount: 0,
    status: "running",
    ...overrides,
  };
}

function row(overrides: Partial<HistoryResultRow> = {}): HistoryResultRow {
  const base: HistoryResultRow = {
    id: "",
    localId: "a_group:job:scan_1",
    symbol: "RELIANCE",
    instrumentType: "FUTURE",
    strategy: "GFS",
    timeframe: null,
    status: "QUALIFIED",
    price: 2900,
    rsi: 65,
    signal: "QUALIFIED",
    aDate: null,
    bDate: null,
    aPrice: null,
    bPrice: null,
    aRsi: null,
    bRsi: null,
    abDistance: null,
    details: "",
    createdAt: "2026-09-22T06:06:00.000Z",
    updatedAt: "2026-09-22T06:06:00.000Z",
    ...overrides,
  };
  base.id = resultRowKey(base);
  return base;
}

beforeEach(async () => {
  await clearAllHistory().catch(() => undefined);
});

describe("localHistoryDb", () => {
  it("persists a scan snapshot", async () => {
    await putSnapshot(meta());
    const found = await getSnapshot("a_group:job:scan_1");
    expect(found?.totalStocks).toBe(615);
    expect(found?.status).toBe("running");
  });

  it("persists a single completed stock immediately", async () => {
    await putSnapshot(meta());
    await putResults([row({ symbol: "AARTIIND" })]);
    const rows = await getResultsForSnapshot("a_group:job:scan_1");
    expect(rows).toHaveLength(1);
    expect(rows[0].symbol).toBe("AARTIIND");
  });

  it("persists many stocks progressively (simulated 310 of 615)", async () => {
    await putSnapshot(meta());
    for (let i = 0; i < 310; i++) {
      await putResults([row({ symbol: `STOCK${i}` })]);
    }
    const rows = await getResultsForSnapshot("a_group:job:scan_1");
    expect(rows).toHaveLength(310);
  });

  it("upserts by deterministic key — reprocessing the same stock never duplicates it", async () => {
    await putSnapshot(meta());
    const r1 = row({ symbol: "TCS", strategy: "PRD", status: "PRD_FORMING", rsi: 60 });
    await putResults([r1]);
    // Same (symbol, strategy, timeframe, A date) reprocessed with an updated value.
    const r2 = row({ symbol: "TCS", strategy: "PRD", status: "PRD_FORMING", rsi: 62 });
    await putResults([r2]);
    const rows = await getResultsForSnapshot("a_group:job:scan_1");
    expect(rows).toHaveLength(1);
    expect(rows[0].rsi).toBe(62); // latest value won, not a duplicate row
  });

  it("keeps a failed stock's record instead of losing it", async () => {
    await putSnapshot(meta());
    await putResults([row({ symbol: "XYZFAIL", strategy: "", status: "DATA_UNAVAILABLE", details: "timeout" })]);
    const rows = await getResultsForSnapshot("a_group:job:scan_1");
    expect(rows.find((r) => r.symbol === "XYZFAIL")?.status).toBe("DATA_UNAVAILABLE");
  });

  it("keeps multiple scans on the same date as separate snapshots", async () => {
    await putSnapshot(meta({ localId: "a_group:job:scan_morning", scanTime: "10:30:00" }));
    await putSnapshot(meta({ localId: "a_group:job:scan_afternoon", scanTime: "16:45:00" }));
    const all = await listSnapshots();
    const sameDate = all.filter((s) => s.scanDate === "2026-09-22");
    expect(sameDate).toHaveLength(2);
    expect(new Set(sameDate.map((s) => s.localId)).size).toBe(2);
  });

  it("reports storage usage stats", async () => {
    await putSnapshot(meta());
    await putResults([row({ symbol: "A" }), row({ symbol: "B" })]);
    const stats = await storageStats();
    expect(stats.scans).toBe(1);
    expect(stats.stocks).toBe(2);
  });
});
