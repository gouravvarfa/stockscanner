import type { SystemOneBacktest } from "./systemOneBacktestApi";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

// The GFS backtest returns exactly the System One result shape (daily candles).
export type GFSBacktest = SystemOneBacktest;

export type GfsVariant = "gfs" | "advanced" | "gfs50";

function gfsPath(variant: GfsVariant): string {
  return variant === "advanced" ? "advanced-gfs" : variant === "gfs50" ? "gfs50" : "gfs";
}

export function gfsExportUrl(variant: GfsVariant, id: string): string {
  return `${API_BASE}/api/${gfsPath(variant)}/backtest/${id}/export`;
}

export async function runGfsBacktest(variant: GfsVariant, req: {
  symbol: string;
  from_date: string;
  to_date: string;
}): Promise<GFSBacktest> {
  const res = await fetch(`${API_BASE}/api/${gfsPath(variant)}/backtest`, {
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

export interface GfsUniverseRow {
  symbol: string;
  company_name: string;
  data_from: string;
  data_to: string;
  close: number;
  daily_rsi: number | null;
  weekly_rsi: number | null;
  monthly_rsi: number | null;
  in_setup_since: string;
}

export interface GfsUniverse {
  status: "idle" | "running" | "done" | "error";
  total: number;
  processed: number;
  failed: number;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  rows: GfsUniverseRow[];
}

/** Route of a variant's backtest page (also the prefix of its all-stocks page). */
export function gfsPagePath(variant: GfsVariant): string {
  return variant === "advanced" ? "/strategies/advanced-gfs" : variant === "gfs50" ? "/strategies/gfs-50" : "/strategies/gfs";
}

async function universeRequest(variant: GfsVariant, path: string, init?: RequestInit): Promise<GfsUniverse> {
  const res = await fetch(`${API_BASE}/api/${gfsPath(variant)}/${path}`, init);
  if (!res.ok) throw new Error(`Could not load the stock list: ${res.status} ${await res.text()}`);
  return res.json() as Promise<GfsUniverse>;
}

export function startGfsUniverse(variant: GfsVariant, fresh = false): Promise<GfsUniverse> {
  return universeRequest(variant, "universe/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fresh }),
  });
}

export function getGfsUniverse(variant: GfsVariant): Promise<GfsUniverse> {
  return universeRequest(variant, "universe");
}
