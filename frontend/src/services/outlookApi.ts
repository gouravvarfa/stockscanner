const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

export interface OutlookRange {
  days: number;
  move_1s: number;
  move_pct_1s: number;
  low_1s: number;
  high_1s: number;
  low_2s: number;
  high_2s: number;
}
export interface OutlookSnapshot {
  as_of: string;
  nifty: {
    close: number; date: string; dma50: number | null; dma200: number | null; trend: string;
    vix: number; vix_date: string; vix_band: string; ranges: { week: OutlookRange; month: OutlookRange };
  };
  commodities: { symbol: string; name: string; close?: number; date?: string; vol?: number; error?: string;
    ranges?: { week: OutlookRange; month: OutlookRange } }[];
}

export async function getOutlook(): Promise<OutlookSnapshot> {
  const res = await fetch(`${API_BASE}/api/outlook`);
  if (!res.ok) {
    let detail = `Request failed: ${res.status}`;
    try { detail = ((await res.json()) as { detail?: string }).detail ?? detail; } catch { /* not JSON */ }
    throw new Error(detail);
  }
  return (await res.json()) as OutlookSnapshot;
}
