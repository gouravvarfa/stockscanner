const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

async function request<T>(path: string): Promise<T | null> {
  const res = await fetch(`${API_BASE}${path}`);
  if (res.status === 404) return null; // no scan cached yet — not an error state
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status}`);
  return res.json() as Promise<T>;
}

export interface StrengthBreakdownOut {
  strength: number | null;
  components: Record<string, number | null>;
}

export interface RankedCandidateOut {
  symbol: string;
  instrument_type?: "FUTURE" | "EQUITY";
  score: number;
  best_strategy: string;
  strategies: string[];
  strategy_breakdown: Record<string, StrengthBreakdownOut>;
}

export interface LatestRankingOut {
  generated_at: string;
  scan_completed_at: string;
  top_candidates: RankedCandidateOut[];
  strategy_best: Record<string, RankedCandidateOut | null>;
  total_candidates: number;
}

export const rankingApi = {
  latest: () => request<LatestRankingOut>("/api/ranking/latest"),
};
