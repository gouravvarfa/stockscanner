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
// v2: RESULTS_STORE moved from an autoIncrement numeric id to a
// deterministic string key (see resultRowKey below) so a re-processed
// stock (page refresh re-fetching the same partial/progress items, a
// retried poll, etc.) overwrites its own row instead of creating a
// duplicate — required for "reconnect/retry cannot create duplicates".
// v3: + SCAN_CACHE_STORE (device-local 24h scan-result cache, see
// getLocalScanCache below). Additive — v2 stores are untouched.
const DB_VERSION = 3;
const SNAPSHOTS_STORE = "snapshots"; // one row per scan (metadata)
const RESULTS_STORE = "results"; // many rows per scan (one per stock/strategy/timeframe row)
const SCAN_CACHE_STORE = "scan_cache"; // one row per scan type: its latest full result, 24h TTL

/** Deterministic per-row key: same (scan, symbol, strategy, timeframe, A
 *  date) always maps to the same IndexedDB row, so `putResults` is a true
 *  upsert — re-writing it (e.g. after a refresh replays the same partial
 *  items) updates that one row instead of adding a duplicate. */
export function resultRowKey(row: {
  localId: string;
  symbol: string;
  strategy: string;
  timeframe: string | null;
  aDate: string | null;
}): string {
  return [row.localId, row.symbol, row.strategy, row.timeframe ?? "", row.aDate ?? ""].join("::");
}

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
  id: string; // deterministic key — see resultRowKey()
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
    req.onupgradeneeded = (event) => {
      const db = req.result;
      // Versioned schema migration: snapshot metadata (scan list) is never
      // touched. RESULTS_STORE's key scheme changed in v2 (see DB_VERSION
      // comment) — an existing v1 store (autoIncrement ids, no natural
      // upsert key) is recreated rather than migrated row-by-row, since
      // every row it held is also re-derivable from a completed scan's
      // cached result; only mid-scan rows from a scan that was never
      // finished before the upgrade are not recoverable, which is the same
      // outcome as that scan being interrupted.
      if (!db.objectStoreNames.contains(SNAPSHOTS_STORE)) {
        const snap = db.createObjectStore(SNAPSHOTS_STORE, { keyPath: "localId" });
        snap.createIndex("byDate", "scanDate");
        snap.createIndex("byScanType", "scanType");
        snap.createIndex("byStartedAt", "startedAt");
      }
      const oldVersion = event.oldVersion;
      if (oldVersion > 0 && oldVersion < 2 && db.objectStoreNames.contains(RESULTS_STORE)) {
        db.deleteObjectStore(RESULTS_STORE);
      }
      if (!db.objectStoreNames.contains(RESULTS_STORE)) {
        const res = db.createObjectStore(RESULTS_STORE, { keyPath: "id" });
        res.createIndex("byLocalId", "localId");
        res.createIndex("bySymbol", "symbol");
      }
      if (!db.objectStoreNames.contains(SCAN_CACHE_STORE)) {
        db.createObjectStore(SCAN_CACHE_STORE, { keyPath: "scanType" });
      }
    };
    req.onsuccess = () => {
      const opened = req.result;
      // Another tab upgrading the schema: release this connection so the
      // upgrade isn't blocked; the next call here reopens at the new version.
      opened.onversionchange = () => {
        opened.close();
        dbPromise = null;
      };
      resolve(opened);
    };
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

// ---------------------------------------------------------------------------
// Device-local scan-result cache (2026-09-25)
//
// The browser's own copy of each scan type's latest full result, with the
// same 24h lifetime as the backend's cache. Read FIRST on page load and on a
// normal Scan, so a refresh — or a Render restart/cold start — never loses
// the last result on this device. IndexedDB is per-browser-profile, so every
// device keeps its own independent cache. Large results never go to
// localStorage. Anything unreadable/expired is deleted and treated as a miss.
// ---------------------------------------------------------------------------

export const LOCAL_SCAN_CACHE_TTL_MS = 24 * 60 * 60 * 1000;

/** Same shape as the backend's CacheEnvelope (services/scanJobsApi.ts). */
export interface LocalScanCacheEnvelope<T = unknown> {
  scan_type: string;
  result: T;
  data_timestamp: string;
  completed_at: string;
  provider: string;
}

interface LocalScanCacheRow {
  scanType: string;
  envelope: LocalScanCacheEnvelope;
  savedAt: string;
}

function isValidRow(row: unknown, scanType: string): row is LocalScanCacheRow {
  if (!row || typeof row !== "object") return false;
  const r = row as Partial<LocalScanCacheRow>;
  const env = r.envelope as Partial<LocalScanCacheEnvelope> | undefined;
  return (
    r.scanType === scanType &&
    !!env &&
    typeof env === "object" &&
    env.result !== undefined &&
    env.result !== null &&
    typeof env.completed_at === "string" &&
    !Number.isNaN(Date.parse(env.completed_at))
  );
}

/** Valid (<24h old, well-formed) cached envelope for `scanType`, or null.
 *  Never throws: IndexedDB unavailable, corrupt or expired all mean "miss"
 *  (corrupt/expired rows are deleted so they can't be served later). */
export async function getLocalScanCache<T = unknown>(
  scanType: string,
  now: number = Date.now(),
): Promise<LocalScanCacheEnvelope<T> | null> {
  try {
    const row = await tx([SCAN_CACHE_STORE], "readonly", (t) => reqToPromise(t.objectStore(SCAN_CACHE_STORE).get(scanType)));
    if (row === undefined) return null;
    if (!isValidRow(row, scanType) || now - Date.parse(row.envelope.completed_at) >= LOCAL_SCAN_CACHE_TTL_MS) {
      await deleteLocalScanCache(scanType);
      return null;
    }
    return row.envelope as LocalScanCacheEnvelope<T>;
  } catch {
    return null;
  }
}

/** Upserts `scanType`'s cached result (one row per type — a new save replaces the old). */
export async function putLocalScanCache(scanType: string, envelope: LocalScanCacheEnvelope): Promise<void> {
  try {
    const row: LocalScanCacheRow = { scanType, envelope, savedAt: new Date().toISOString() };
    await tx([SCAN_CACHE_STORE], "readwrite", (t) => {
      t.objectStore(SCAN_CACHE_STORE).put(row);
    });
  } catch {
    // Best-effort: a failed local save (quota, private mode) just means the
    // next load falls back to the backend, exactly as before.
  }
}

export async function deleteLocalScanCache(scanType: string): Promise<void> {
  try {
    await tx([SCAN_CACHE_STORE], "readwrite", (t) => {
      t.objectStore(SCAN_CACHE_STORE).delete(scanType);
    });
  } catch {
    // nothing to clean up
  }
}
