import type { SystemOneBacktest } from "./systemOneBacktestApi";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

// The GFS backtest returns exactly the System One result shape (daily candles).
export type GFSBacktest = SystemOneBacktest;

export async function runGfsBacktest(req: {
  symbol: string;
  from_date: string;
  to_date: string;
}): Promise<GFSBacktest> {
  const res = await fetch(`${API_BASE}/api/gfs/backtest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const body = await res.text();
    let detail: string | undefined;
    try {
      detail = (JSON.parse(body) as { detail?: string }).detail;
    } catch {
      // not JSON
    }
    throw new Error(detail ?? `Backtest failed: ${res.status} ${body}`);
  }
  return res.json() as Promise<GFSBacktest>;
}
