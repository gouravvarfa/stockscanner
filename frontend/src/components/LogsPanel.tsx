import { useEffect, useRef, useState } from "react";
import { api, type LogEntry } from "../services/api";

const POLL_INTERVAL_MS = 1500;
const MAX_LINES = 500;

function levelClass(level: string): string {
  const l = level.toUpperCase();
  if (l === "ERROR" || l === "CRITICAL") return "log-line log-line-error";
  if (l === "WARNING") return "log-line log-line-warning";
  return "log-line";
}

export function LogsPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [lines, setLines] = useState<LogEntry[]>([]);
  const [paused, setPaused] = useState(false);
  const lastIdRef = useRef(0);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const pausedRef = useRef(paused);

  useEffect(() => {
    pausedRef.current = paused;
  }, [paused]);

  useEffect(() => {
    if (!open) return;

    let cancelled = false;

    function poll() {
      if (pausedRef.current) return;
      api
        .getLogs(lastIdRef.current)
        .then((entries) => {
          if (cancelled || entries.length === 0) return;
          lastIdRef.current = entries[entries.length - 1].id;
          setLines((prev) => [...prev, ...entries].slice(-MAX_LINES));
        })
        .catch(() => undefined);
    }

    // Seed with recent history on open, then start incremental polling.
    api
      .getLogs(0, 200)
      .then((entries) => {
        if (cancelled) return;
        lastIdRef.current = entries.length > 0 ? entries[entries.length - 1].id : 0;
        setLines(entries);
      })
      .catch(() => undefined);

    const id = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [open]);

  useEffect(() => {
    if (open && !paused) bottomRef.current?.scrollIntoView({ block: "end" });
  }, [lines, open, paused]);

  return (
    <>
      {open && <div className="logs-panel-backdrop" onClick={onClose} />}
      <aside className={open ? "logs-panel open" : "logs-panel"}>
        <div className="logs-panel-header">
          <span>Live Logs</span>
          <div className="logs-panel-actions">
            <button className="secondary-button" onClick={() => setPaused((p) => !p)}>
              {paused ? "Resume" : "Pause"}
            </button>
            <button className="secondary-button" onClick={() => setLines([])}>
              Clear
            </button>
            <button className="icon-button" onClick={onClose} aria-label="Close logs panel">
              ✕
            </button>
          </div>
        </div>
        <div className="logs-panel-body">
          {lines.length === 0 ? (
            <p className="muted small">No logs yet — run a scan to see live activity.</p>
          ) : (
            lines.map((l) => (
              <div key={l.id} className={levelClass(l.level)}>
                <span className="log-time">{l.timestamp.slice(11, 19)}</span>
                <span className="log-message">{l.message}</span>
              </div>
            ))
          )}
          <div ref={bottomRef} />
        </div>
      </aside>
    </>
  );
}
