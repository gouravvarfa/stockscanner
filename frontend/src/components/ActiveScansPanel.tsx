import { useEffect, useRef, useState } from "react";
import { scanJobsApi, fmtDuration, scanTypeLabel, type ScanJobOut } from "../services/scanJobsApi";

const POLL_MS = 2000;

/**
 * Mounted once at the App shell level (survives every route change) — polls
 * every job the backend knows about and shows the ones currently running,
 * regardless of which page started them or which page is open now. This is
 * what makes Part 3 ("global running scan dashboard") true: the user always
 * knows what's happening, even mid-navigation.
 */
export function ActiveScansPanel() {
  const [jobs, setJobs] = useState<ScanJobOut[]>([]);
  const [collapsed, setCollapsed] = useState(false);
  const [dismissedCompleted, setDismissedCompleted] = useState<Set<string>>(new Set());
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let stopped = false;
    const tick = async () => {
      try {
        const all = await scanJobsApi.listJobs();
        if (!stopped) setJobs(all);
      } catch {
        // Transient network hiccup — just try again on the next tick.
      }
      if (!stopped) timer.current = setTimeout(tick, POLL_MS);
    };
    void tick();
    return () => {
      stopped = true;
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  const running = jobs.filter((j) => j.status === "running");
  const recentlyDone = jobs
    .filter((j) => j.status !== "running" && !dismissedCompleted.has(j.job_id))
    .slice(0, 3);
  const visible = [...running, ...recentlyDone];

  if (visible.length === 0) return null;

  return (
    <div className="active-scans-panel">
      <div className="active-scans-header" onClick={() => setCollapsed((v) => !v)}>
        <span>
          Active Scans {running.length > 0 && <span className="active-scans-badge">{running.length}</span>}
        </span>
        <span className="active-scans-toggle">{collapsed ? "▲" : "▼"}</span>
      </div>
      {!collapsed && (
        <div className="active-scans-body">
          {visible.map((job) => (
            <div key={job.job_id} className="active-scan-row">
              <div className="active-scan-row-top">
                <span className="active-scan-name">{scanTypeLabel(job.scan_type)}</span>
                {job.status === "running" ? (
                  <span className="active-scan-pct">{job.percentage.toFixed(0)}%</span>
                ) : (
                  <button
                    className="active-scan-dismiss"
                    onClick={() => setDismissedCompleted((s) => new Set(s).add(job.job_id))}
                    aria-label="Dismiss"
                  >
                    ✕
                  </button>
                )}
              </div>
              {job.status === "running" ? (
                <>
                  <div className="active-scan-bar">
                    <div className="active-scan-bar-fill" style={{ width: `${Math.min(job.percentage, 100)}%` }} />
                  </div>
                  <div className="active-scan-meta">
                    {job.processed} / {job.total || "?"} stocks
                    {job.current_symbol && <> · {job.current_symbol}</>}
                  </div>
                  <div className="active-scan-meta">
                    Elapsed {fmtDuration(job.elapsed_seconds)} · ETA{" "}
                    {job.eta_seconds === null ? "Estimating…" : fmtDuration(job.eta_seconds)}
                  </div>
                  {job.failed > 0 && <div className="active-scan-meta active-scan-warn">{job.failed} failed</div>}
                </>
              ) : (
                <div className={`active-scan-meta ${job.status === "failed" ? "active-scan-warn" : ""}`}>
                  {job.status === "completed" && `Completed · ${job.successful}/${job.processed} successful`}
                  {job.status === "failed" && `Failed: ${job.error ?? "unknown error"}`}
                  {job.status === "cancelled" && "Cancelled"}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
