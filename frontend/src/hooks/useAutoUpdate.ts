import { useEffect, useState } from "react";

/**
 * Auto-update (2026-11-22): every 15 seconds, and whenever the window comes back into view, the app asks for
 * /version.json. When a newer deploy is live it shows a short notice and reloads itself - no manual refresh.
 * Running scans live on the server, so a reload just reconnects to them. Dev builds (no version.json) never reload.
 */
const CHECK_EVERY_MS = 15_000; // a new deploy shows up within ~15 s

export function useAutoUpdate(): boolean {
  const [updating, setUpdating] = useState(false);
  useEffect(() => {
    if (import.meta.env.DEV) return;
    let stopped = false;
    const check = async () => {
      if (stopped) return;
      try {
        const res = await fetch(`/version.json?t=${Date.now()}`, { cache: "no-store" });
        if (!res.ok) return;
        const { build } = (await res.json()) as { build?: string };
        if (build && build !== __BUILD_ID__) {
          stopped = true;
          setUpdating(true);
          window.setTimeout(() => window.location.reload(), 1200);
        }
      } catch {
        /* offline or Vercel unreachable: try again later */
      }
    };
    const id = window.setInterval(check, CHECK_EVERY_MS);
    const onVisible = () => { if (document.visibilityState === "visible") void check(); };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onVisible);
    void check();
    return () => {
      stopped = true;
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onVisible);
    };
  }, []);
  return updating;
}
