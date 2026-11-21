import { saveBlob } from "./breakout15Api";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

export type Signal = "Leader" | "Turning up" | "Fading" | "Laggard" | "N/A";
export type Verdict = "STRONG" | "MIXED" | "WEAK" | "N/A";

export interface SectorStock {
  symbol: string;
  name: string | null;
  industry: string | null;
  r1w: number;
  r1m: number;
  vs1w: number;
  vs1m: number;
  signal: Signal;
  group: "Near-leader" | "Bounce-only" | null;
  combined: number;
  sector?: string;
}

export interface SectorRow {
  key: string;
  label: string;
  index_label: string | null;
  equal_weight: boolean;
  end_date: string | null;
  r1w: number | null;
  r1m: number | null;
  rank_1w: number | null;
  rank_1m: number | null;
  rsi: { d: number | null; w: number | null; m: number | null };
  verdict: Verdict;
  stocks: SectorStock[];
  counts: Record<string, number>;
  members: number;
  beat_1w: number;
  beat_1m: number;
}

export interface WeeklyReport {
  as_of: string;
  end_date: string | null;
  benchmark: { label: string; r1w: number | null; r1m: number | null };
  rules: { strong_rsi: number; weak_rsi: number; near_pp: number };
  sectors: SectorRow[];
  top_movers: SectorStock[];
  laggards: SectorStock[];
  buckets: Record<"strength_leaders" | "watch" | "stock_specific" | "relative_weakness", Record<string, string[]>>;
  summary: {
    top_sector: string | null;
    top_sector_r1w: number | null;
    top_sector_r1m: number | null;
    strong_sectors: string[];
    leaders: number;
    laggards: number;
    rows: number;
    stocks: number;
  };
  missing: string[];
  generated_at: string;
  constituents_source?: string;
}

export interface WeeklyJob {
  job_id: string;
  as_of: string;
  status: "running" | "done" | "failed";
  done: number;
  total: number;
  phase: string;
  current: string;
  error: string | null;
  result?: WeeklyReport;
}

async function errorText(res: Response): Promise<string> {
  try {
    const body = await res.json();
    return typeof body?.detail === "string" ? body.detail : `HTTP ${res.status}`;
  } catch {
    return `HTTP ${res.status}`;
  }
}

export async function startWeeklyReport(asOf: string): Promise<WeeklyJob> {
  const res = await fetch(`${API_BASE}/api/weekly-sectors/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ as_of: asOf || null }),
  });
  if (!res.ok) throw new Error(await errorText(res));
  return res.json();
}

export async function getWeeklyJob(jobId: string): Promise<WeeklyJob> {
  const res = await fetch(`${API_BASE}/api/weekly-sectors/run/${encodeURIComponent(jobId)}`);
  if (!res.ok) throw new Error(await errorText(res));
  return res.json();
}

async function download(path: string, report: WeeklyReport, filename: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/weekly-sectors/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(report),
  });
  if (!res.ok) throw new Error(await errorText(res));
  saveBlob(await res.blob(), filename);
}

export function downloadWeeklyPdf(report: WeeklyReport): Promise<void> {
  return download("pdf", report, `weekly_sector_report_${report.end_date ?? report.as_of}.pdf`);
}

export function downloadWeeklyXlsx(report: WeeklyReport): Promise<void> {
  return download("export", report, `weekly_sectors_${report.end_date ?? report.as_of}.xlsx`);
}

// The last report stays on this device, so reopening the page shows it without running anything.
const LAST_KEY = "weekly-sectors:last";

export function loadLastReport(): WeeklyReport | null {
  try {
    const raw = localStorage.getItem(LAST_KEY);
    return raw ? (JSON.parse(raw) as WeeklyReport) : null;
  } catch {
    return null;
  }
}

export function saveLastReport(report: WeeklyReport): void {
  try {
    localStorage.setItem(LAST_KEY, JSON.stringify(report));
  } catch {
    // storage full or blocked: the report is still on screen
  }
}
