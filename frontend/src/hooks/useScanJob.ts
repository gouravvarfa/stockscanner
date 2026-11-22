import { useCallback, useEffect, useRef, useState } from "react";
import {
  scanJobsApi,
  ScanApiError,
  type CacheEnvelope,
  type PartialResult,
  type ProgressLogItem,
  type ScanJobOut,
  type ScanType,
} from "../services/scanJobsApi";
import { KEEP_UNTIL_DELETED, deleteLocalScanCache, getLocalScanCache, putLocalScanCache } from "../services/localHistoryDb";

const POLL_INTERVAL_MS = 1500;

/** Device-local cache (IndexedDB, 24h) for a result this device just received. */
function saveLocal<T>(scanType: ScanType, result: T, completedAt: string | null | undefined, provider = "angel_one"): void {
  const at = completedAt && !Number.isNaN(Date.parse(completedAt)) ? completedAt : new Date().toISOString();
  void putLocalScanCache(scanType, { scan_type: scanType, result, data_timestamp: at, completed_at: at, provider });
}

// A Render restart (deploy, OOM recovery, or the free instance waking from
// sleep) can leave the backend unreachable for tens of seconds. A single
// failed poll must not permanently stop polling a job that is actually
// still running server-side — keep retrying, with backoff so a restarting
// instance isn't hammered, for up to this long before giving up.
// 2026-11-20: was 60 s. An out-of-memory restart on Render (the instance hangs, is killed, restarts and cold
// starts) took longer than that, so polling gave up just before the server came back and the scan looked stuck.
const RECOVERY_WINDOW_MS = 5 * 60_000;
const POLL_BACKOFF_START_MS = 1500;
const POLL_BACKOFF_MAX_MS = 6000;
const POLL_BACKOFF_FACTOR = 1.6;

function nextBackoffDelay(consecutiveFailures: number): number {
  const delay = POLL_BACKOFF_START_MS * Math.pow(POLL_BACKOFF_FACTOR, consecutiveFailures);
  return Math.min(delay, POLL_BACKOFF_MAX_MS);
}

// The very first request (Run Scan/Fresh Scan itself, before any job/poll
// exists to retry) can hit the same kind of outage. Retries a plain
// network-level failure (not a real API error like 400/409) a few times
// before surfacing it, so one click during an outage doesn't require a
// second manual click.
const START_RETRY_ATTEMPTS = 4;
const START_RETRY_DELAY_MS = 4000;

async function withColdStartRetry<T>(fn: () => Promise<T>): Promise<T> {
  for (let attempt = 1; ; attempt++) {
    try {
      return await fn();
    } catch (e) {
      const isNetworkFailure = !(e instanceof ScanApiError); // a real API error (4xx/5xx) reached the server — don't retry those
      if (!isNetworkFailure || attempt >= START_RETRY_ATTEMPTS) throw e;
      await new Promise((resolve) => setTimeout(resolve, START_RETRY_DELAY_MS));
    }
  }
}

/** Distinguishes WHY polling stopped, so the UI never shows a generic
 *  "Failed to fetch" for something the user can act on differently:
 *   - "unavailable": backend unreachable this whole window; may still recover.
 *   - "interrupted": backend responded but confirmed the job is gone (a
 *     restart wiped the in-memory job registry) — retrying can't help,
 *     the scan is genuinely lost; the user just starts a new one.
 *   - "error": a real scan/job failure reported by the backend.
 */
export type ScanIssueKind = "unavailable" | "interrupted" | "error" | null;

// When a restart wiped a running scan, it is started again automatically - at most AUTO_RESTART_MAX times per
// AUTO_RESTART_WINDOW_MS per scan type, so a scan that keeps crashing the server cannot loop forever.
export const AUTO_RESTART_MAX = 2;
const AUTO_RESTART_WINDOW_MS = 60 * 60_000;

export function takeAutoRestartSlot(scanType: string, now: number = Date.now()): boolean {
  const key = `scan-auto-restarts:${scanType}`;
  let stamps: number[] = [];
  try {
    const raw = JSON.parse(localStorage.getItem(key) ?? "[]");
    if (Array.isArray(raw)) stamps = raw.filter((t): t is number => typeof t === "number");
  } catch {
    stamps = [];
  }
  stamps = stamps.filter((t) => now - t < AUTO_RESTART_WINDOW_MS);
  if (stamps.length >= AUTO_RESTART_MAX) return false;
  stamps.push(now);
  try {
    localStorage.setItem(key, JSON.stringify(stamps));
  } catch {
    // storage blocked: the restart still happens, the cap just is not remembered across reloads
  }
  return true;
}

interface UseScanJobResult<T> {
  result: T | null;
  partial: PartialResult[]; // stocks that already qualified, streamed while the job runs
  progressLog: ProgressLogItem[]; // EVERY processed stock (success or fail), streamed while the job runs
  job: ScanJobOut | null; // live progress while a job is running/just finished
  running: boolean;
  error: string | null;
  issueKind: ScanIssueKind;
  cache: CacheEnvelope<T> | null; // metadata of the cached result currently shown, if any
  run: () => Promise<void>; // Normal Scan: serves cache if valid, else starts a job
  runFresh: () => Promise<void>; // Fresh Scan: always starts a new job
  cancel: () => Promise<void>;
  clearSaved: () => Promise<void>; // delete this device's saved result
  queued: string | null; // waiting for another big scan to finish; starts by itself
}

/**
 * Backend owns the job (backend/services/scan_job_manager.py) — this hook
 * only starts jobs, polls their progress, and restores state on mount. It
 * does NOT execute anything itself, so navigating away and back (or a full
 * browser refresh) just resumes polling the same still-running job, and a
 * finished job's result is read back from GET /api/scan/jobs/{id}/results
 * or the 24h cache — never re-run client-side.
 */
export interface UseScanJobOptions<T> {
  /** Saved results (device cache, server cache, an earlier job) are shown only when this returns true - e.g. the
   *  Dashboard refuses the old whole-A-Group results now that it scans only the STRONG sectors (2026-11-22). */
  accept?: (result: T) => boolean;
}

export function useScanJob<T = unknown>(scanType: ScanType, options: UseScanJobOptions<T> = {}): UseScanJobResult<T> {
  const acceptRef = useRef(options.accept);
  acceptRef.current = options.accept;
  const usable = (r: T | null | undefined): r is T => r !== null && r !== undefined && (!acceptRef.current || acceptRef.current(r));
  const [result, setResult] = useState<T | null>(null);
  const [job, setJob] = useState<ScanJobOut | null>(null);
  const [running, setRunning] = useState(false);
  const [partial, setPartial] = useState<PartialResult[]>([]);
  const partialCursor = useRef(0);
  const [progressLog, setProgressLog] = useState<ProgressLogItem[]>([]);
  const progressCursor = useRef(0);
  const [error, setError] = useState<string | null>(null);
  const [issueKind, setIssueKind] = useState<ScanIssueKind>(null);
  // Queue (2026-11-22): another big scan already running on the server -> wait and start by itself, never stop it.
  const [queued, setQueued] = useState<string | null>(null);
  const queueTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const clearQueue = () => {
    if (queueTimer.current) clearTimeout(queueTimer.current);
    queueTimer.current = null;
    setQueued(null);
  };
  const heavyBusy = (e: unknown) => e instanceof ScanApiError && e.status === 429 && /another big scan/i.test(e.message);
  const queueRetry = (e: unknown, again: () => void) => {
    const m = /\(([a-z_]+)\)/.exec(e instanceof Error ? e.message : "");
    const name = m ? ({ a_group: "Dashboard scan", cup_breakout: "Cup Breakout scan", value_buy: "Value Buy scan" } as Record<string, string>)[m[1]] ?? m[1] : "big scan";
    setQueued(`Queued — starts by itself when the running ${name} finishes (the server runs one big scan at a time).`);
    if (queueTimer.current) clearTimeout(queueTimer.current);
    queueTimer.current = setTimeout(again, 15_000);
  };
  const [cache, setCache] = useState<CacheEnvelope<T> | null>(null);

  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activeJobId = useRef<string | null>(null);
  const pollGeneration = useRef(0); // bumped every pollJob() call, even for the same job id — see pollJob below
  const consecutiveFailures = useRef(0);
  const firstFailureAt = useRef<number | null>(null);
  const restartNote = useRef<string | null>(null); // shown while an automatically restarted scan runs

  const stopPolling = useCallback(() => {
    if (pollTimer.current) {
      clearTimeout(pollTimer.current);
      pollTimer.current = null;
    }
  }, []);

  const pollJob = useCallback(
    (jobId: string) => {
      // A fresh generation for EVERY call, even a repeat call for the SAME
      // job id (e.g. the mount-time restore already polling this job, and
      // then a 409-adopt from a manual Run Scan click for that same job) —
      // comparing only activeJobId.current would let two concurrent tick
      // loops for the same job both run forever, each independently
      // appending to `partial`/`progressLog` and duplicating every chip.
      stopPolling();
      const myGeneration = ++pollGeneration.current;
      activeJobId.current = jobId;
      partialCursor.current = 0;
      progressCursor.current = 0;
      consecutiveFailures.current = 0;
      firstFailureAt.current = null;
      setPartial([]);
      setProgressLog([]);
      const tick = async () => {
        if (activeJobId.current !== jobId || pollGeneration.current !== myGeneration) return; // superseded
        try {
          const latest = await scanJobsApi.getJob(jobId);
          if (activeJobId.current !== jobId || pollGeneration.current !== myGeneration) return;
          // Recovered from any prior outage — clear it and keep going normally.
          consecutiveFailures.current = 0;
          firstFailureAt.current = null;
          setError(latest.status === "running" ? restartNote.current : null);
          setIssueKind(null);
          setJob(latest);
          if (latest.status !== "running") restartNote.current = null;
          // Incremental results: only what is newer than the cursor is fetched/appended.
          if (latest.signals_found > 0 || partialCursor.current > 0) {
            try {
              const inc = await scanJobsApi.getPartial(jobId, partialCursor.current);
              if (activeJobId.current === jobId && pollGeneration.current === myGeneration && inc.items.length > 0) {
                partialCursor.current = inc.next;
                setPartial((prev) => prev.concat(inc.items));
              }
            } catch {
              // partial view is best-effort; the final result still arrives on completion
            }
          }
          // EVERY processed stock (success or fail), for the local
          // history writer to persist a gap-free record — best-effort,
          // same as partial above.
          if (latest.processed > 0 || progressCursor.current > 0) {
            try {
              const prog = await scanJobsApi.getProgressLog(jobId, progressCursor.current);
              if (activeJobId.current === jobId && pollGeneration.current === myGeneration && prog.items.length > 0) {
                progressCursor.current = prog.next;
                setProgressLog((prev) => prev.concat(prog.items));
              }
            } catch {
              // best-effort — local history just won't have every non-qualifying stock this tick
            }
          }
          if (latest.status === "running") {
            setRunning(true);
            pollTimer.current = setTimeout(tick, POLL_INTERVAL_MS);
            return;
          }
          setRunning(false);
          if (latest.status === "completed") {
            try {
              const r = await scanJobsApi.getJobResults<T>(jobId);
              if (activeJobId.current === jobId && pollGeneration.current === myGeneration) {
                setResult(r);
                setCache(null); // freshly computed, not from the pre-existing cache envelope
                saveLocal(scanType, r, latest.completion_time);
                if (KEEP_UNTIL_DELETED.has(scanType)) {
                  // saved on this laptop's disk -> the server forgets its copy (Cup Breakout, 2026-11-22)
                  const at = latest.completion_time ?? new Date().toISOString();
                  void putLocalScanCache(scanType, { scan_type: scanType, result: r, data_timestamp: at, completed_at: at, provider: "angel_one" })
                    .then(() => scanJobsApi.forgetJob(jobId))
                    .catch(() => undefined);
                }
              }
            } catch (e) {
              setIssueKind("error");
              setError(e instanceof Error ? e.message : String(e));
            }
          } else if (latest.status === "failed") {
            setIssueKind("error");
            setError(latest.error ?? "Scan failed.");
          }
        } catch (e) {
          if (activeJobId.current !== jobId || pollGeneration.current !== myGeneration) return;

          // A definitive "the job is gone" answer (backend is back up and
          // says so) — a restart wiped the in-memory registry. This is NOT
          // a transient outage: no amount of retrying will bring it back,
          // so stop immediately instead of burning the recovery window.
          if (e instanceof ScanApiError && e.status === 404) {
            activeJobId.current = null;
            stopPolling();
            setJob(null);
            // Start it again automatically (2026-11-20) instead of leaving the scan stuck.
            if (takeAutoRestartSlot(scanType)) {
              try {
                const res = await withColdStartRetry(() => scanJobsApi.fresh<T>(scanType));
                if (res.status === "started") {
                  restartNote.current = "The server restarted, so this scan was started again automatically.";
                  setIssueKind(null);
                  setError(restartNote.current);
                  setJob(res.job);
                  setRunning(true);
                  pollJob(res.job.job_id);
                  return;
                }
              } catch {
                // e.g. another device's big scan is running (one at a time on Render): show the notice below
              }
            }
            setRunning(false);
            setIssueKind("interrupted");
            setError("Backend restarted — previous scan was interrupted.");
            return;
          }

          // Anything else (network failure, 5xx, etc.) is treated as a
          // temporary outage — keep the current progress UI up, keep
          // retrying with backoff, for up to RECOVERY_WINDOW_MS.
          if (firstFailureAt.current === null) firstFailureAt.current = Date.now();
          consecutiveFailures.current += 1;
          const elapsed = Date.now() - firstFailureAt.current;
          if (elapsed < RECOVERY_WINDOW_MS) {
            setIssueKind("unavailable");
            setError(`${e instanceof Error ? e.message : String(e)} — retrying…`);
            pollTimer.current = setTimeout(tick, nextBackoffDelay(consecutiveFailures.current));
            return;
          }

          // Recovery window exhausted — stop polling; the user can retry manually.
          setRunning(false);
          setIssueKind("unavailable");
          setError(e instanceof Error ? e.message : String(e));
        }
      };
      void tick();
    },
    [stopPolling, scanType],
  );

  const run = useCallback(async () => {
    setError(null);
    setIssueKind(null);
    // Normal Scan: a valid (<24h) result already on THIS device is used
    // directly — no network call, works even while Render is restarting.
    const local = await getLocalScanCache<T>(scanType);
    if (local && usable(local.result)) {
      setResult(local.result);
      setCache(local as CacheEnvelope<T>);
      setJob(null);
      setRunning(false);
      return;
    }
    if (local) await deleteLocalScanCache(scanType); // an older kind of result: not shown, not kept
    try {
      const res = await withColdStartRetry(() => scanJobsApi.start<T>(scanType));
      clearQueue();
      if (res.status === "cached") {
        setResult(res.cache.result);
        setCache(res.cache);
        setJob(null);
        setRunning(false);
        saveLocal(scanType, res.cache.result, res.cache.completed_at, res.cache.provider);
      } else {
        setJob(res.job);
        setRunning(true);
        pollJob(res.job.job_id);
      }
    } catch (e) {
      if (e instanceof ScanApiError && e.status === 409) {
        // Already running (e.g. from another tab/page, or this same device
        // clicking Run Scan again) — the backend tells us exactly which
        // job_id that is; just adopt/poll it directly instead of erroring
        // out (no separate list-and-guess lookup, which could race and
        // miss it if the job had just changed state).
        if (e.jobId) {
          try {
            const existing = await scanJobsApi.getJob(e.jobId);
            setJob(existing);
            setRunning(existing.status === "running");
            if (existing.status === "running") {
              pollJob(existing.job_id);
            }
            return;
          } catch {
            // fall through to the generic error below
          }
        }
      }
      if (heavyBusy(e)) {
        queueRetry(e, () => void runRef.current());
        return;
      }
      setIssueKind("error");
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [scanType, pollJob]);

  const runFresh = useCallback(async () => {
    setError(null);
    setIssueKind(null);
    // 2026-11-22: the saved result stays (on screen and on this device) until the new scan replaces it.
    try {
      const res = await withColdStartRetry(() => scanJobsApi.fresh<T>(scanType));
      clearQueue();
      if (res.status === "started") {
        setJob(res.job);
        setRunning(true);
        setCache(null);
        pollJob(res.job.job_id);
      }
    } catch (e) {
      if (heavyBusy(e)) {
        queueRetry(e, () => void runFreshRef.current());
        return;
      }
      setIssueKind("error");
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [scanType, pollJob]);
  const runRef = useRef(run);
  const runFreshRef = useRef(runFresh);
  runRef.current = run;
  runFreshRef.current = runFresh;

  const cancel = useCallback(async () => {
    clearQueue();
    if (job?.job_id) {
      // Optimistic: stop polling and flip back to Run/Fresh Scan immediately,
      // rather than waiting up to POLL_INTERVAL_MS for the next poll to see
      // status "cancelled". Cancellation is a plain stop, so there is no
      // result to lose by not waiting for the server's confirmation.
      activeJobId.current = null;
      stopPolling();
      setRunning(false);
      try {
        await scanJobsApi.cancelJob(job.job_id);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    }
  }, [job, stopPolling]);

  // Restore-on-mount (Part 6): a running job for this scan type takes
  // priority (resume polling it); otherwise fall back to a valid 24h
  // cache, if one exists — no new scan is ever triggered just by mounting.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      // 1) This device's own cache first: shown immediately, before (and
      //    regardless of) any backend round-trip — survives refreshes and
      //    Render restarts/cold starts.
      const found = await getLocalScanCache<T>(scanType);
      if (cancelled) return;
      const local = found && usable(found.result) ? found : null;
      if (local) {
        setResult(local.result);
        setCache(local as CacheEnvelope<T>);
      }
      try {
        // 2) A scan still running for this device takes over the view.
        const jobs = await scanJobsApi.listJobs();
        const inFlight = jobs.find((j) => j.scan_type === scanType && j.status === "running");
        if (cancelled) return;
        if (inFlight) {
          setJob(inFlight);
          setRunning(true);
          pollJob(inFlight.job_id);
          return;
        }
        if (local) return; // valid local cache — no need to download it again
        // 3) Cache miss: fetch from the backend, then keep a local copy.
        const mostRecent = jobs.find((j) => j.scan_type === scanType && j.status === "completed");
        if (mostRecent) {
          try {
            const r = await scanJobsApi.getJobResults<T>(mostRecent.job_id);
            if (!cancelled && usable(r)) {
              setResult(r);
              setJob(mostRecent);
              saveLocal(scanType, r, mostRecent.completion_time);
            }
            return;
          } catch {
            // fall through to cache below
          }
        }
        const cached = await scanJobsApi.getCache<T>(scanType).catch(() => null);
        if (!cancelled && cached && usable(cached.result)) {
          setResult(cached.result);
          setCache(cached);
          saveLocal(scanType, cached.result, cached.completed_at, cached.provider);
        }
      } catch {
        // Best-effort restore only — a failure here just means the page
        // starts blank, same as before this feature existed.
      }
    })();
    return () => {
      cancelled = true;
      activeJobId.current = null;
      stopPolling();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scanType]);

  // Delete this device's saved result (the copy on the laptop's disk) and clear the screen.
  const clearSaved = useCallback(async () => {
    await deleteLocalScanCache(scanType);
    setResult(null);
    setCache(null);
  }, [scanType]);

  return { result, partial, progressLog, job, running, error, issueKind, cache, run, runFresh, cancel, clearSaved, queued };
}
