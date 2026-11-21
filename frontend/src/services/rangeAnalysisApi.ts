import { saveBlob } from "./breakout15Api";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

export type RangeLevel = "green" | "orange" | "plain" | "none";

export interface RangeCell {
  pct: number;
  direction: "up" | "down";
  level: RangeLevel;
  in_progress: boolean;
  boxed: boolean;
}

export interface RangeRow {
  year: number;
  months: (RangeCell | null)[];
  avg: number | null;
  complete_months: number;
}

export interface RangeMonthStat {
  month: string;
  years: number;
  avg: number | null;
  median: number | null;
  ge20: number;
  ge30: number;
  max: number | null;
  min: number | null;
}

export interface RangeTable {
  symbol: string;
  name: string | null;
  kind: "EQUITY" | "INDEX";
  thresholds: { orange: number; green: number };
  data_from: string;
  data_to: string;
  filter_from: string;
  filter_to: string;
  rows: RangeRow[];
  month_stats: RangeMonthStat[];
  jan_mar: { ge30: Record<string, number>; best: string[] };
  overall: { months: number; avg: number | null; median: number | null; ge20: number; ge30: number; most_active: string | null; quietest: string | null };
  monthly: unknown[];
}

export interface RangeSearchHit {
  symbol: string;
  name: string | null;
  kind: "EQUITY" | "INDEX";
}

async function errorText(res: Response): Promise<string> {
  try {
    const body = await res.json();
    return typeof body?.detail === "string" ? body.detail : `HTTP ${res.status}`;
  } catch {
    return `HTTP ${res.status}`;
  }
}

export async function searchRangeInstruments(q: string): Promise<RangeSearchHit[]> {
  const res = await fetch(`${API_BASE}/api/range-analysis/search?q=${encodeURIComponent(q)}`);
  if (!res.ok) throw new Error(await errorText(res));
  return res.json();
}

/** from / to: "YYYY-MM" (or empty for the whole history). */
export async function fetchRangeTable(symbol: string, from: string, to: string): Promise<RangeTable> {
  const qs = new URLSearchParams();
  if (from) qs.set("from_date", from);
  if (to) qs.set("to_date", to);
  const res = await fetch(`${API_BASE}/api/range-analysis/stock/${encodeURIComponent(symbol)}?${qs.toString()}`);
  if (!res.ok) throw new Error(await errorText(res));
  return res.json();
}

export function rangeExportName(t: Pick<RangeTable, "symbol" | "filter_from" | "filter_to">): string {
  return `${t.symbol}_range_move_${t.filter_from}_to_${t.filter_to}.xlsx`;
}

/** The Excel is built from the table already on screen: nothing is fetched again or stored on the server. */
export async function downloadRangeXlsx(table: RangeTable): Promise<void> {
  const res = await fetch(`${API_BASE}/api/range-analysis/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(table),
  });
  if (!res.ok) throw new Error(await errorText(res));
  saveBlob(await res.blob(), rangeExportName(table));
}
