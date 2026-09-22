import { createContext, useContext, type ReactNode } from "react";
import type { ScanResult } from "../services/api";
import { useScanJob } from "../hooks/useScanJob";
import { useLocalHistoryWriter } from "../hooks/useLocalHistoryWriter";
import type { PartialResult } from "../services/scanJobsApi";

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
}

const ScanContext = createContext<ScanContextValue | undefined>(undefined);

export function ScanProvider({ children }: { children: ReactNode }) {
  const { result, partial, job, running, error, cache, run, runFresh, cancel } = useScanJob<ScanResult>("a_group");

  // Permanent, device-local Scan History (IndexedDB) — writes progressively
  // as results arrive, independent of Render's own storage. See
  // hooks/useLocalHistoryWriter.ts.
  useLocalHistoryWriter("a_group", job, partial, result);

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
        runScan: run,
        runFreshScan: runFresh,
        stopScan: cancel,
        progress,
        partial,
        cacheAgeSeconds,
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
