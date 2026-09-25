import "fake-indexeddb/auto";
import { IDBFactory } from "fake-indexeddb";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

type Db = typeof import("./localHistoryDb");

/** A fresh module instance = what a page refresh gets: no in-memory state,
 *  only whatever is really persisted in IndexedDB. */
async function freshModule(): Promise<Db> {
  vi.resetModules();
  return import("./localHistoryDb");
}

const HOUR = 60 * 60 * 1000;
const COMPLETED = "2026-09-25T10:00:00.000Z";
const completedMs = Date.parse(COMPLETED);

function envelope(result: unknown = { results: [{ symbol: "SONACOMS", status: "NEAR_BREAKOUT" }] }) {
  return { scan_type: "cup_breakout", result, data_timestamp: COMPLETED, completed_at: COMPLETED, provider: "angel_one" };
}

const originalFactory = globalThis.indexedDB;

beforeEach(() => {
  // Each test starts from an empty browser profile.
  globalThis.indexedDB = new IDBFactory();
});

afterEach(() => {
  globalThis.indexedDB = originalFactory;
});

describe("device-local scan cache (IndexedDB)", () => {
  it("saves and loads a scan result", async () => {
    const db = await freshModule();
    await db.putLocalScanCache("cup_breakout", envelope());
    const got = await db.getLocalScanCache("cup_breakout", completedMs + HOUR);
    expect(got?.result).toEqual(envelope().result);
    expect(got?.completed_at).toBe(COMPLETED);
  });

  it("keeps one entry per scan type (a new save replaces the old; types don't mix)", async () => {
    const db = await freshModule();
    await db.putLocalScanCache("cup_breakout", envelope({ v: 1 }));
    await db.putLocalScanCache("cup_breakout", envelope({ v: 2 }));
    await db.putLocalScanCache("a_group", { ...envelope({ other: true }), scan_type: "a_group" });
    expect((await db.getLocalScanCache("cup_breakout", completedMs))?.result).toEqual({ v: 2 });
    expect((await db.getLocalScanCache("a_group", completedMs))?.result).toEqual({ other: true });
  });

  it("survives a page refresh (new module instance, same IndexedDB)", async () => {
    const before = await freshModule();
    await before.putLocalScanCache("cup_breakout", envelope());
    const afterRefresh = await freshModule();
    expect((await afterRefresh.getLocalScanCache("cup_breakout", completedMs + HOUR))?.result).toEqual(envelope().result);
  });

  it("expires after 24 hours and deletes the expired row", async () => {
    const db = await freshModule();
    await db.putLocalScanCache("cup_breakout", envelope());
    expect(await db.getLocalScanCache("cup_breakout", completedMs + 23.9 * HOUR)).not.toBeNull();
    expect(await db.getLocalScanCache("cup_breakout", completedMs + 24 * HOUR)).toBeNull();
    // Deleted, not just hidden: even an "earlier" clock can't resurrect it.
    expect(await db.getLocalScanCache("cup_breakout", completedMs)).toBeNull();
  });

  it("Fresh Scan invalidation removes only that scan type's cache", async () => {
    const db = await freshModule();
    await db.putLocalScanCache("cup_breakout", envelope());
    await db.putLocalScanCache("a_group", { ...envelope(), scan_type: "a_group" });
    await db.deleteLocalScanCache("cup_breakout");
    expect(await db.getLocalScanCache("cup_breakout", completedMs)).toBeNull();
    expect(await db.getLocalScanCache("a_group", completedMs)).not.toBeNull();
  });

  it("different devices (separate IndexedDB) are completely independent", async () => {
    const deviceA = globalThis.indexedDB;
    const a = await freshModule();
    await a.putLocalScanCache("cup_breakout", envelope({ device: "A" }));

    globalThis.indexedDB = new IDBFactory(); // device B: its own browser storage
    const b = await freshModule();
    expect(await b.getLocalScanCache("cup_breakout", completedMs)).toBeNull();
    await b.putLocalScanCache("cup_breakout", envelope({ device: "B" }));

    globalThis.indexedDB = deviceA;
    const aAgain = await freshModule();
    expect((await aAgain.getLocalScanCache("cup_breakout", completedMs))?.result).toEqual({ device: "A" });
  });

  it("recovers from a corrupt entry: treated as a miss and removed", async () => {
    const db = await freshModule();
    await db.putLocalScanCache("cup_breakout", envelope()); // creates the DB/store
    // Overwrite with garbage directly, as a bad write / old schema would leave it.
    await new Promise<void>((resolve, reject) => {
      const req = indexedDB.open("scanner_local_history");
      req.onsuccess = () => {
        const t = req.result.transaction(["scan_cache"], "readwrite");
        t.objectStore("scan_cache").put({ scanType: "cup_breakout", envelope: { result: null, completed_at: "not-a-date" } });
        t.oncomplete = () => {
          req.result.close();
          resolve();
        };
        t.onerror = () => reject(t.error);
      };
      req.onerror = () => reject(req.error);
    });
    const reloaded = await freshModule();
    expect(await reloaded.getLocalScanCache("cup_breakout", completedMs)).toBeNull();
    // A good save afterwards works normally.
    await reloaded.putLocalScanCache("cup_breakout", envelope());
    expect(await reloaded.getLocalScanCache("cup_breakout", completedMs)).not.toBeNull();
  });

  it("never throws when IndexedDB is unavailable (e.g. blocked/private mode)", async () => {
    // @ts-expect-error simulate a browser without IndexedDB
    globalThis.indexedDB = undefined;
    const db = await freshModule();
    await expect(db.putLocalScanCache("cup_breakout", envelope())).resolves.toBeUndefined();
    await expect(db.getLocalScanCache("cup_breakout")).resolves.toBeNull();
  });
});
