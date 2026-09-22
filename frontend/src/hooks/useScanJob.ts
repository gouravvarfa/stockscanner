import { useCallback, useEffect, useRef, useState } from "react";
import { scanJobsApi, ScanApiError, type CacheEnvelope, type PartialResult, type ScanJobOut, type ScanType } from "../services/scanJobsApi";

const POLL_INTERVAL_MS = 1500;
// A single fetch failure (e.g. Render's free-tier instance still waking up
// from sleep) must not permanently stop polling a job that is actually
// still running server-side — retry transient failures for a while before
// giving up, instead of dying on the first one.
const MAX_CONSECUTIVE_POLL_FAILURES = 20; // ~30s of retries at POLL_INTERVAL_MS

// Render's free instance can take 30-60s to wake from sleep — the very
// first request (Run Scan/Fresh Scan itself, before any job/poll exists
// to retry) can hit that cold start too. Retries a plain network-level
// failure (not a real API error like 400/404/409) a few times before
// surfacing it, so one click during a cold start doesn't require a
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

interface UseScanJobResult<T> {
  result: T | null;
  partial: PartialResult[]; // stocks that already qualified, streamed while the job runs
  job: ScanJobOut | null; // live progress while a job is running/just finished
  running: boolean;
  error: string | null;
  cache: CacheEnvelope<T> | null; // metadata of the cached result currently shown, if any
  run: () => Promise<void>; // Normal Scan: serves cache if valid, else starts a job
  runFresh: () => Promise<void>; // Fresh Scan: always starts a new job
  cancel: () => Promise<void>;
}

/**
 * Backend owns the job (backend/services/scan_job_manager.py) — this hook
 * only starts jobs, polls their progress, and restores state on mount. It
 * does NOT execute anything itself, so navigating away and back (or a full
 * browser refresh) just resumes polling the same still-running job, and a
 * finished job's result is read back from GET /api/scan/jobs/{id}/results
 * or the 24h cache — never re-run client-side.
 */
export function useScanJob<T = unknown>(scanType: ScanType): UseScanJobResult<T> {
  const [result, setResult] = useState<T | null>(null);
  const [job, setJob] = useState<ScanJobOut | null>(null);
  const [running, setRunning] = useState(false);
  const [partial, setPartial] = useState<PartialResult[]>([]);
  const partialCursor = useRef(0);
  const [error, setError] = useState<string | null>(null);
  const [cache, setCache] = useState<CacheEnvelope<T> | null>(null);

  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activeJobId = useRef<string | null>(null);
  const consecutiveFailures = useRef(0);

  const stopPolling = useCallback(() => {
    if (pollTimer.current) {
      clearTimeout(pollTimer.current);
      pollTimer.current = null;
    }
  }, []);

  const pollJob = useCallback(
    (jobId: string) => {
      activeJobId.current = jobId;
      partialCursor.current = 0;
      setPartial([]);
      const tick = async () => {
        if (activeJobId.current !== jobId) return; // superseded by a newer job
        try {
          const latest = await scanJobsApi.getJob(jobId);
          if (activeJobId.current !== jobId) return;
          consecutiveFailures.current = 0;
          setError(null); // a prior transient failure recovered — clear the stale banner
          setJob(latest);
          // Incremental results: only what is newer than the cursor is fetched/appended.
          if (latest.signals_found > 0 || partialCursor.current > 0) {
            try {
              const inc = await scanJobsApi.getPartial(jobId, partialCursor.current);
              if (activeJobId.current === jobId && inc.items.length > 0) {
                partialCursor.current = inc.next;
                setPartial((prev) => prev.concat(inc.items));
              }
            } catch {
              // partial view is best-effort; the final result still arrives on completion
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
              if (activeJobId.current === jobId) {
                setResult(r);
                setCache(null); // freshly computed, not from the pre-existing cache envelope
              }
            } catch (e) {
              setError(e instanceof Error ? e.message : String(e));
            }
          } else if (latest.status === "failed") {
            setError(latest.error ?? "Scan failed.");
          }
        } catch (e) {
          if (activeJobId.current !== jobId) return;
          consecutiveFailures.current += 1;
          if (consecutiveFailures.current < MAX_CONSECUTIVE_POLL_FAILURES) {
            // Likely transient (e.g. the backend waking up from sleep) — keep
            // showing "running" and keep polling instead of giving up on the
            // first hiccup; only surface the error as a soft, still-retrying note.
            setError(`${e instanceof Error ? e.message : String(e)} — retrying…`);
            pollTimer.current = setTimeout(tick, POLL_INTERVAL_MS);
            return;
          }
          setRunning(false);
          setError(e instanceof Error ? e.message : String(e));
        }
      };
      void tick();
    },
    [],
  );

  const run = useCallback(async () => {
    setError(null);
    try {
      const res = await withColdStartRetry(() => scanJobsApi.start<T>(scanType));
      if (res.status === "cached") {
        setResult(res.cache.result);
        setCache(res.cache);
        setJob(null);
        setRunning(false);
      } else {
        setJob(res.job);
        setRunning(true);
        pollJob(res.job.job_id);
      }
    } catch (e) {
      if (e instanceof ScanApiError && e.status === 409) {
        // Already running (e.g. from another tab/page) — just start
        // polling whatever job is in flight instead of erroring out.
        const jobs = await scanJobsApi.listJobs();
        const inFlight = jobs.find((j) => j.scan_type === scanType && j.status === "running");
        if (inFlight) {
          setJob(inFlight);
          setRunning(true);
          pollJob(inFlight.job_id);
          return;
        }
      }
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [scanType, pollJob]);

  const runFresh = useCallback(async () => {
    setError(null);
    try {
      const res = await withColdStartRetry(() => scanJobsApi.fresh<T>(scanType));
      if (res.status === "started") {
        setJob(res.job);
        setRunning(true);
        setCache(null);
        pollJob(res.job.job_id);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [scanType, pollJob]);

  const cancel = useCallback(async () => {
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
      try {
        const jobs = await scanJobsApi.listJobs();
        const inFlight = jobs.find((j) => j.scan_type === scanType && j.status === "running");
        if (cancelled) return;
        if (inFlight) {
          setJob(inFlight);
          setRunning(true);
          pollJob(inFlight.job_id);
          return;
        }
        const mostRecent = jobs.find((j) => j.scan_type === scanType && j.status === "completed");
        if (mostRecent) {
          try {
            const r = await scanJobsApi.getJobResults<T>(mostRecent.job_id);
            if (!cancelled) {
              setResult(r);
              setJob(mostRecent);
            }
            return;
          } catch {
            // fall through to cache below
          }
        }
        const cached = await scanJobsApi.getCache<T>(scanType).catch(() => null);
        if (!cancelled && cached) {
          setResult(cached.result);
          setCache(cached);
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

  return { result, partial, job, running, error, cache, run, runFresh, cancel };
}
