import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import type { ScanResult } from "../services/api";
import { useScanJob, type ScanIssueKind } from "../hooks/useScanJob";
import { useLocalHistoryWriter } from "../hooks/useLocalHistoryWriter";
import { localIdForJob } from "../services/historyRowMapping";
import { getResultsForSnapshot, listSnapshots, type HistoryResultRow } from "../services/localHistoryDb";
import type { PartialResult } from "../services/scanJobsApi";

const SCAN_TYPE = "a_group";

interface ScanContextValue {
  latest: ScanResult | null;
  setLatest: (result: ScanResult | null) => void;
  // Scan-in-progress state lives here (not in the Dashboard page component)
  // specifically so it survives navigating to another page. As of the
  // background Scan Job Manager, the scan itself runs entirely server-side
  // (backend/services/scan_job_manager.py) — this context now just starts
  // the job and polls its progress via useScanJob, so the same "survives
  // navigation" behavior now ALSO survives a full browser refresh, and
  // exposes real per-stock progress instead of a bare boolean.
  scanning: boolean;
  scanError: string | null;
  // Distinguishes a temporary outage (may still recover) from a confirmed
  // "the backend restarted and the job is gone" from a plain scan/job
  // error — see hooks/useScanJob.ts.
  scanIssueKind: ScanIssueKind;
  runScan: () => Promise<void>;
  // Fresh Scan (Part 9): ignores the 24h cache and always re-fetches from
  // Angel One, replacing the cache only on success.
  runFreshScan: () => Promise<void>;
  stopScan: () => Promise<void>;
  progress: {
    processed: number;
    total: number;
    percentage: number;
    currentSymbol: string | null;
    elapsedSeconds: number;
    etaSeconds: number | null;
    signalsFound: number;
    failed: number;
  } | null;
  partial: PartialResult[];
  cacheAgeSeconds: number | null;
  // The device's own permanent local record of the current/most-recent scan
  // (IndexedDB — see services/localHistoryDb.ts). Loaded immediately on
  // mount/refresh, before the backend has even responded, and kept in sync
  // as new stocks are persisted — so a page refresh (or a Render restart
  // that leaves the job unrecoverable) never blanks out results that were
  // already saved to this device.
  localRows: HistoryResultRow[];
}

const ScanContext = createContext<ScanContextValue | undefined>(undefined);

export function ScanProvider({ children }: { children: ReactNode }) {
  const { result, partial, progressLog, job, running, error, issueKind, cache, run, runFresh, cancel } =
    useScanJob<ScanResult>(SCAN_TYPE);

  // Permanent, device-local Scan History (IndexedDB) — writes progressively
  // as results arrive, independent of Render's own storage. See
  // hooks/useLocalHistoryWriter.ts.
  useLocalHistoryWriter(SCAN_TYPE, job, partial, progressLog, result);

  const [localRows, setLocalRows] = useState<HistoryResultRow[]>([]);
  const localIdRef = useRef<string | null>(null);
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Immediate local view on mount/refresh — reads whatever this device
  // already has saved, before waiting on any backend response.
  useEffect(() => {
    let cancelled = false;
    listSnapshots().then((snapshots) => {
      const mostRecent = snapshots.find((s) => s.scanType === SCAN_TYPE);
      if (!mostRecent || cancelled) return;
      localIdRef.current = mostRecent.localId;
      getResultsForSnapshot(mostRecent.localId).then((rows) => {
        if (!cancelled) setLocalRows(rows);
      });
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // Keep the local view in sync as the live job writes new rows — reads
  // IndexedDB back (rather than mirroring `partial`/`progressLog` in memory)
  // so what's shown always matches what's actually durably saved, deduped
  // by the store's own deterministic keys.
  useEffect(() => {
    if (!job) return;
    const localId = localIdForJob(SCAN_TYPE, job.job_id);
    localIdRef.current = localId;
    if (refreshTimer.current) clearTimeout(refreshTimer.current);
    refreshTimer.current = setTimeout(() => {
      getResultsForSnapshot(localId).then(setLocalRows).catch(() => undefined);
    }, 400); // debounced — avoid re-reading IndexedDB on every single stock
    return () => {
      if (refreshTimer.current) clearTimeout(refreshTimer.current);
    };
  }, [job, partial, progressLog]);

  const progress =
    job && job.status === "running"
      ? {
          processed: job.processed,
          total: job.total,
          percentage: job.percentage,
          currentSymbol: job.current_symbol,
          elapsedSeconds: job.elapsed_seconds,
          etaSeconds: job.eta_seconds,
          signalsFound: job.signals_found,
          failed: job.failed,
        }
      : null;

  const cacheAgeSeconds = cache ? (Date.now() - new Date(cache.completed_at).getTime()) / 1000 : null;

  return (
    <ScanContext.Provider
      value={{
        latest: result,
        // setLatest is kept for API compatibility with any existing caller
        // that wants to clear/override the displayed result client-side
        // (e.g. after Reset) — it does not affect the backend job/cache.
        setLatest: () => {},
        scanning: running,
        scanError: error,
        scanIssueKind: issueKind,
        runScan: run,
        runFreshScan: runFresh,
        stopScan: cancel,
        progress,
        partial,
        cacheAgeSeconds,
        localRows,
      }}
    >
      {children}
    </ScanContext.Provider>
  );
}

export function useScan(): ScanContextValue {
  const ctx = useContext(ScanContext);
  if (!ctx) throw new Error("useScan must be used within ScanProvider");
  return ctx;
}
