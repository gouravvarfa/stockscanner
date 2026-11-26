import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import {
  getWeeklyJob,
  loadLastReport,
  saveLastReport,
  startWeeklyReport,
  type WeeklyJob,
  type WeeklyReport,
} from "../services/weeklySectorsApi";

/**
 * The Weekly Sectors report run, kept at app level (2026-11-22): the report keeps running - and its progress keeps
 * showing - when you open another page, and the running job's id is remembered on this device, so even a page refresh
 * picks it up again. Weekly Sectors and Heatmap both read the same report from here.
 */

const JOB_KEY = "weekly-sectors:job";
const POLL_MS = 1500;
const AUTO_GAP_MS = 45 * 60_000;

interface WeeklyReportValue {
  report: WeeklyReport | null;
  job: WeeklyJob | null;
  running: boolean;
  error: string | null;
  /** asOf: YYYY-MM-DD, or "" for the latest close. */
  run: (asOf?: string) => Promise<void>;
  /** Runs the latest report on its own when the one on this device is stale (at most every 45 minutes). */
  ensureFresh: () => void;
}

/** IST wall clock as a Date whose UTC fields are IST. */
const istNow = (now: Date) => new Date(now.getTime() + 330 * 60_000);
/** The latest NSE close (15:30 IST on a weekday) at or before now, as a real timestamp. */
export function lastClose(now = new Date()): Date {
  const d = istNow(now);
  for (let i = 0; i < 8; i++) {
    const day = d.getUTCDay();
    const close = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), 15, 30) - 330 * 60_000;
    if (day !== 0 && day !== 6 && close <= now.getTime()) return new Date(close);
    d.setUTCDate(d.getUTCDate() - 1);
  }
  return new Date(0);
}
/** 2026-11-24 (user: Heatmap and Weekly Sectors update by themselves): a report is stale when it was made before the
 *  last close, or - while the market is open - when it is over an hour old. */
export function isStale(generatedAt: string | undefined, now = new Date()): boolean {
  if (!generatedAt) return true;
  const made = new Date(generatedAt).getTime();
  if (!Number.isFinite(made)) return true;
  if (made < lastClose(now).getTime()) return true;
  const ist = istNow(now);
  const mins = ist.getUTCHours() * 60 + ist.getUTCMinutes();
  const open = ist.getUTCDay() !== 0 && ist.getUTCDay() !== 6 && mins >= 9 * 60 + 15 && mins < 15 * 60 + 30;
  return open && now.getTime() - made > 60 * 60_000;
}

const WeeklyReportContext = createContext<WeeklyReportValue | undefined>(undefined);

function rememberJob(id: string | null): void {
  try {
    if (id) localStorage.setItem(JOB_KEY, id);
    else localStorage.removeItem(JOB_KEY);
  } catch {
    // storage blocked: the run still works, it just is not picked up again after a refresh
  }
}

export function WeeklyReportProvider({ children }: { children: ReactNode }) {
  const [report, setReport] = useState<WeeklyReport | null>(() => loadLastReport());
  const [job, setJob] = useState<WeeklyJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const watching = useRef<string | null>(null);

  const finish = useCallback((j: WeeklyJob) => {
    setJob(j);
    rememberJob(null);
    watching.current = null;
    if (j.status === "done" && j.result) {
      setReport(j.result);
      saveLastReport(j.result);
    } else if (j.status === "failed") {
      setError(j.error ?? "The report could not be built.");
    }
  }, []);

  const watch = useCallback(
    (jobId: string) => {
      if (timer.current) clearTimeout(timer.current);
      watching.current = jobId;
      const tick = async () => {
        if (watching.current !== jobId) return;
        try {
          const next = await getWeeklyJob(jobId);
          if (watching.current !== jobId) return;
          if (next.status === "running") {
            setJob(next);
            timer.current = setTimeout(tick, POLL_MS);
          } else finish(next);
        } catch (e) {
          if (watching.current !== jobId) return;
          watching.current = null;
          rememberJob(null);
          setJob(null);
          setError(e instanceof Error ? e.message : String(e));
        }
      };
      timer.current = setTimeout(tick, 400);
    },
    [finish],
  );

  const run = useCallback(
    async (asOf = "") => {
      setError(null);
      try {
        const j = await startWeeklyReport(asOf);
        if (j.status !== "running") return finish(j);
        setJob(j);
        rememberJob(j.job_id);
        watch(j.job_id);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [finish, watch],
  );

  // 2026-11-26: not once per app session - the app stays open all day, so a report from the morning was never
  // refreshed after the close. Any stale report runs again, at most once per AUTO_GAP_MS.
  const lastAuto = useRef(0);
  const ensureFresh = useCallback(() => {
    if (job?.status === "running" || watching.current) return;
    if (!isStale(report?.generated_at)) return;
    if (Date.now() - lastAuto.current < AUTO_GAP_MS) return;
    lastAuto.current = Date.now();
    void run("");
  }, [job?.status, report?.generated_at, run]);

  // 2026-11-26: the evening job builds the report from NSE end-of-day data (/eod/weekly.json), so it is up to date
  // even when nobody opened the app. Used when it is newer than the report on this device.
  useEffect(() => {
    let alive = true;
    fetch(`/eod/weekly.json?d=${new Date().toISOString().slice(0, 10)}`, { cache: "no-cache" })
      .then((r) => (r.ok ? r.json() : null))
      .then((eod: WeeklyReport | null) => {
        if (!alive || !eod?.generated_at) return;
        setReport((cur) => {
          if (cur && new Date(cur.generated_at).getTime() >= new Date(eod.generated_at).getTime()) return cur;
          saveLastReport(eod);
          return eod;
        });
      })
      .catch(() => undefined);
    return () => { alive = false; };
  }, []);

  // A run that was still going when this page was last open (or refreshed): pick it up again.
  useEffect(() => {
    let id: string | null = null;
    try {
      id = localStorage.getItem(JOB_KEY);
    } catch {
      id = null;
    }
    if (id) {
      setJob({ job_id: id, as_of: "", status: "running", done: 0, total: 0, phase: "Reconnecting to the running report…", current: "", error: null });
      watch(id);
    }
    return () => {
      if (timer.current) clearTimeout(timer.current);
      watching.current = null;
    };
  }, [watch]);

  return (
    <WeeklyReportContext.Provider value={{ report, job, running: job?.status === "running", error, run, ensureFresh }}>
      {children}
    </WeeklyReportContext.Provider>
  );
}

export function useWeeklyReport(): WeeklyReportValue {
  const ctx = useContext(WeeklyReportContext);
  if (!ctx) throw new Error("useWeeklyReport must be used within WeeklyReportProvider");
  return ctx;
}
