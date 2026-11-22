const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

export interface GannProjectionRef {
  label: string;
  source_date: string;
  count: number;
}

export interface GannCluster {
  date: string;
  bars_away: number; // 0 = last candle, 1 = next trading day, negative = window still open
  strength: number;
  projections: GannProjectionRef[];
}

export interface GannSector {
  sector: string;
  stocks: number;
  ret_1m: number;
  ret_3m: number;
  score: number;
  strong: boolean;
}

export interface GannStockRow {
  symbol: string;
  company_name: string;
  sector: string;
  close: number;
  ret_1m: number | null;
  ret_3m: number | null;
  last_pivot_kind: "H" | "L" | null;
  last_pivot_date: string | null;
  new_swing_forming: boolean;
  clusters: GannCluster[];
}

export interface GannSectorScan {
  status: "idle" | "running" | "done" | "error";
  total: number;
  processed: number;
  failed: number;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  nifty_1m: number | null;
  nifty_3m: number | null;
  sectors: GannSector[];
  rows: GannStockRow[];
}

export interface GannStockDetail {
  symbol: string;
  company_name: string;
  sector: string | null;
  last_date: string;
  last_close: number;
  new_swing_forming: boolean;
  candles: { time: number; open: number; high: number; low: number; close: number }[];
  pivots: { date: string; kind: "H" | "L"; price: number }[];
  counts: { from_date: string; from_kind: string; to_date: string; to_kind: string; candles: number }[];
  projections: (GannProjectionRef & { date: string; bars_away: number })[];
  clusters: GannCluster[];
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    const body = await res.text();
    let detail: string | undefined;
    try {
      detail = (JSON.parse(body) as { detail?: string }).detail;
    } catch {
      // not JSON
    }
    throw new Error(detail ?? `Request failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const searchGannStocks = (q: string) =>
  call<{ symbol: string; company_name: string }[]>(`/api/gann-time/search?q=${encodeURIComponent(q)}`);
export const startGannSectors = (fresh: boolean) =>
  call<GannSectorScan>(`/api/gann-time/sectors/start?fresh=${fresh}`, { method: "POST" });
export const getGannSectors = () => call<GannSectorScan>("/api/gann-time/sectors");
export const getGannStock = (symbol: string) =>
  call<GannStockDetail>(`/api/gann-time/stock/${encodeURIComponent(symbol)}`);
