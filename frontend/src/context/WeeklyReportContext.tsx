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

interface WeeklyReportValue {
  report: WeeklyReport | null;
  job: WeeklyJob | null;
  running: boolean;
  error: string | null;
  /** asOf: YYYY-MM-DD, or "" for the latest close. */
  run: (asOf?: string) => Promise<void>;
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
    <WeeklyReportContext.Provider value={{ report, job, running: job?.status === "running", error, run }}>
      {children}
    </WeeklyReportContext.Provider>
  );
}

export function useWeeklyReport(): WeeklyReportValue {
  const ctx = useContext(WeeklyReportContext);
  if (!ctx) throw new Error("useWeeklyReport must be used within WeeklyReportProvider");
  return ctx;
}
