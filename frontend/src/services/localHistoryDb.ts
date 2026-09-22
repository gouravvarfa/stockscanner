/**
 * Permanent, device-local Scan History — browser IndexedDB, never Render.
 *
 * Architecture (per explicit requirement, 2026-09-22):
 *   Angel One -> Render FastAPI backend -> live scan results -> frontend
 *   -> LOCAL IndexedDB -> permanent date-wise Scan History.
 *
 * Render/the scan job manager stays responsible for Angel One calls, market
 * data, strategy calculation, and progressive results (unchanged). This
 * module is only responsible for the browser's OWN permanent copy of those
 * results — it never re-fetches Angel One and never recalculates a
 * strategy; every write is a straight copy of what Render already computed.
 *
 * No third-party IndexedDB library existed in this project (checked before
 * writing this), so this is a small dependency-free wrapper — deliberately
 * NOT a second competing abstraction, since there was no first one.
 *
 * NEVER stored here: Angel One API key, client ID, PIN, TOTP secret, or any
 * access token. Only scan metadata and per-stock strategy results.
 */

const DB_NAME = "scanner_local_history";
const DB_VERSION = 1;
const SNAPSHOTS_STORE = "snapshots"; // one row per scan (metadata)
const RESULTS_STORE = "results"; // many rows per scan (one per qualifying stock/strategy/timeframe row)

export type SnapshotStatus = "running" | "completed" | "stopped" | "failed";

export interface HistorySnapshotMeta {
  localId: string; // stable local key: `${scanType}:${scanId ?? job/started_at}`
  scanId: number | null; // backend scan_id, once known (history_service.persist_scan)
  jobId: string | null; // backend scan job id, if this snapshot was built live
  scanType: string;
  scanDate: string; // YYYY-MM-DD, IST
  scanTime: string; // HH:mm:ss, IST
  startedAt: string; // ISO
  completedAt: string | null; // ISO, null while running
  durationSeconds: number | null;
  totalStocks: number;
  processedStocks: number;
  successfulStocks: number;
  failedStocks: number;
  signalCount: number;
  status: SnapshotStatus;
}

export interface HistoryResultRow {
  id?: number; // IndexedDB autoIncrement key
  localId: string; // FK -> HistorySnapshotMeta.localId
  symbol: string;
  instrumentType: "FUTURE" | "EQUITY" | null;
  strategy: string;
  timeframe: string | null;
  status: string; // e.g. QUALIFIED, PRD_FORMING, PRD_CONFIRMED, DATA_UNAVAILABLE
  price: number | null;
  rsi: number | null;
  signal: string | null;
  aDate: string | null;
  bDate: string | null;
  aPrice: number | null;
  bPrice: number | null;
  aRsi: number | null;
  bRsi: number | null;
  abDistance: number | null;
  details: string;
  createdAt: string;
  updatedAt: string;
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      // Versioned schema migration: only create what's missing, so an
      // existing local database from an earlier version is never wiped.
      if (!db.objectStoreNames.contains(SNAPSHOTS_STORE)) {
        const snap = db.createObjectStore(SNAPSHOTS_STORE, { keyPath: "localId" });
        snap.createIndex("byDate", "scanDate");
        snap.createIndex("byScanType", "scanType");
        snap.createIndex("byStartedAt", "startedAt");
      }
      if (!db.objectStoreNames.contains(RESULTS_STORE)) {
        const res = db.createObjectStore(RESULTS_STORE, { keyPath: "id", autoIncrement: true });
        res.createIndex("byLocalId", "localId");
        res.createIndex("bySymbol", "symbol");
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

let dbPromise: Promise<IDBDatabase> | null = null;
function db(): Promise<IDBDatabase> {
  if (!dbPromise) dbPromise = openDb();
  return dbPromise;
}

function tx<T>(storeNames: string[], mode: IDBTransactionMode, fn: (t: IDBTransaction) => Promise<T> | T): Promise<T> {
  return db().then(
    (d) =>
      new Promise<T>((resolve, reject) => {
        const t = d.transaction(storeNames, mode);
        let result: T;
        t.oncomplete = () => resolve(result);
        t.onerror = () => reject(t.error);
        t.onabort = () => reject(t.error ?? new Error("IndexedDB transaction aborted"));
        Promise.resolve(fn(t)).then((r) => {
          result = r;
        });
      }),
  );
}

function reqToPromise<T>(req: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

// ---------------------------------------------------------------------------
// Snapshots
// ---------------------------------------------------------------------------

export async function putSnapshot(meta: HistorySnapshotMeta): Promise<void> {
  await tx([SNAPSHOTS_STORE], "readwrite", (t) => {
    t.objectStore(SNAPSHOTS_STORE).put(meta);
  });
}

export async function getSnapshot(localId: string): Promise<HistorySnapshotMeta | null> {
  return tx([SNAPSHOTS_STORE], "readonly", async (t) => {
    const r = await reqToPromise(t.objectStore(SNAPSHOTS_STORE).get(localId));
    return (r as HistorySnapshotMeta) ?? null;
  });
}

export async function listSnapshots(): Promise<HistorySnapshotMeta[]> {
  return tx([SNAPSHOTS_STORE], "readonly", async (t) => {
    const all = await reqToPromise(t.objectStore(SNAPSHOTS_STORE).getAll());
    return (all as HistorySnapshotMeta[]).sort((a, b) => b.startedAt.localeCompare(a.startedAt));
  });
}

export async function deleteSnapshot(localId: string): Promise<void> {
  await tx([SNAPSHOTS_STORE, RESULTS_STORE], "readwrite", async (t) => {
    t.objectStore(SNAPSHOTS_STORE).delete(localId);
    const idx = t.objectStore(RESULTS_STORE).index("byLocalId");
    const cursorReq = idx.openCursor(IDBKeyRange.only(localId));
    await new Promise<void>((resolve, reject) => {
      cursorReq.onsuccess = () => {
        const cursor = cursorReq.result;
        if (cursor) {
          cursor.delete();
          cursor.continue();
        } else {
          resolve();
        }
      };
      cursorReq.onerror = () => reject(cursorReq.error);
    });
  });
}

export async function clearAllHistory(): Promise<void> {
  await tx([SNAPSHOTS_STORE, RESULTS_STORE], "readwrite", (t) => {
    t.objectStore(SNAPSHOTS_STORE).clear();
    t.objectStore(RESULTS_STORE).clear();
  });
}

// ---------------------------------------------------------------------------
// Results (batched writes — see LiveHistoryWriter below)
// ---------------------------------------------------------------------------

export async function putResults(rows: HistoryResultRow[]): Promise<void> {
  if (rows.length === 0) return;
  await tx([RESULTS_STORE], "readwrite", (t) => {
    const store = t.objectStore(RESULTS_STORE);
    for (const row of rows) store.put(row);
  });
}

export async function getResultsForSnapshot(localId: string): Promise<HistoryResultRow[]> {
  return tx([RESULTS_STORE], "readonly", async (t) => {
    const idx = t.objectStore(RESULTS_STORE).index("byLocalId");
    const rows = await reqToPromise(idx.getAll(IDBKeyRange.only(localId)));
    return rows as HistoryResultRow[];
  });
}

// ---------------------------------------------------------------------------
// Storage usage (Settings page)
// ---------------------------------------------------------------------------

export async function storageStats(): Promise<{ scans: number; stocks: number; estimatedBytes: number | null }> {
  const snapshots = await listSnapshots();
  const results = await tx([RESULTS_STORE], "readonly", async (t) => reqToPromise(t.objectStore(RESULTS_STORE).count()));
  let estimatedBytes: number | null = null;
  try {
    if (navigator.storage?.estimate) {
      const est = await navigator.storage.estimate();
      estimatedBytes = est.usage ?? null;
    }
  } catch {
    estimatedBytes = null;
  }
  return { scans: snapshots.length, stocks: results as number, estimatedBytes };
}
