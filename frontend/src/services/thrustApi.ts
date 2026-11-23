const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

export interface ThrustHistoryRow {
  date: string;
  from_date: string;
  direction: "up" | "down";
  bars: number;
  pace: number;
  climax: boolean;
  turned: boolean | null;
  back_atr: number | null;
}

export interface ThrustCheck {
  symbol: string;
  company_name: string;
  last_date: string;
  last_close: number;
  status: "stretched" | "fired" | "normal";
  pivot: { kind: "low" | "high"; date: string; price: number };
  direction: "up" | "down";
  bars_since: number;
  atr: number;
  move: number;
  pace: number;
  need_for_thrust: number;
  thrust: { date: string; bars: number; pace: number; climax: boolean; bars_ago: number } | null;
  history: ThrustHistoryRow[];
  own_record: { thrusts: number; turned: number };
  record: { turn_within_3: string; turn_random: string; back_1atr: string; avg_r: string };
}

export async function getThrust(symbol: string): Promise<ThrustCheck> {
  const res = await fetch(`${API_BASE}/api/thrust/stock/${encodeURIComponent(symbol)}`);
  if (!res.ok) {
    let detail: string | undefined;
    try { detail = ((await res.json()) as { detail?: string }).detail; } catch { /* not JSON */ }
    throw new Error(detail ?? `Request failed: ${res.status}`);
  }
  return res.json() as Promise<ThrustCheck>;
}
