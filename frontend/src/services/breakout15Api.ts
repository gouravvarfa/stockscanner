const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { headers: { "Content-Type": "application/json" }, ...options });
  if (!res.ok) {
    let detail: string | undefined;
    try {
      const d = (JSON.parse(await res.text()) as { detail?: unknown }).detail;
      if (typeof d === "string") detail = d;
    } catch {
      // not JSON
    }
    throw new Error(detail ?? `API ${path} failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export type Breakout15Symbol = "NIFTY" | "BANKNIFTY";
export type Breakout15ExitMode = "CLOSE" | "SECOND_LAST";

export interface Breakout15Row {
  date: string;
  first_open: number | null; first_high: number | null; first_low: number | null; first_close: number | null;
  first_range_pct: number | null; first_direction: "Green" | "Red" | "Doji" | null;
  side: "CALL" | "PUT" | "BOTH" | null;
  breakout_time: string | null; entry_price: number | null; stop_loss: number | null;
  second_last_time: string | null; second_last_close: number | null; second_last_change_pct: number | null;
  exit_time: string | null; exit_price: number | null;
  exit_reason: "STOP_LOSS" | "MARKET_CLOSE" | "SECOND_LAST_CLOSE" | "NO_ENTRY" | "DATA_INCOMPLETE" | "DATA_ENDED_BEFORE_CLOSE";
  pnl_points: number | null; pnl_pct: number | null;
  flags: string[]; quality: string;
}

export interface Breakout15Summary {
  trading_days: number; call_entries: number; put_entries: number; both_side_days: number; resolved_days: number; no_entry_days: number; stop_loss_exits: number;
  market_close_exits: number; incomplete_days: number; ambiguous_days: number;
  winning_trades: number; losing_trades: number; win_rate: number | null;
  net_points: number; avg_points: number | null; max_drawdown_points: number;
}

export interface Breakout15Result {
  symbol: Breakout15Symbol; token: string; exit_mode: Breakout15ExitMode; from: string; to: string; generated_at: string;
  summary: Breakout15Summary; rows: Breakout15Row[];
}

export interface Breakout15Job {
  id: string; symbol: Breakout15Symbol; state: "running" | "done" | "error"; phase?: "downloading" | "resolving"; done: number; total: number; error: string | null;
}

export const breakout15Api = {
  start: (symbol: Breakout15Symbol, from_date: string, to_date: string, exit_mode: Breakout15ExitMode) =>
    request<Breakout15Job>("/api/breakout15/runs", { method: "POST", body: JSON.stringify({ symbol, from_date, to_date, exit_mode }) }),
  job: (id: string) => request<Breakout15Job>(`/api/breakout15/runs/${id}`),
  result: (symbol: Breakout15Symbol) => request<Breakout15Result>(`/api/breakout15/results/${symbol}`),
};

export interface ManualRow {
  date: string;
  side: "CALL" | "PUT" | null;
  candle_pct: number | null;
  outcome: "PROFIT" | "LOSS" | null;
  eod_pct: number | null;
}

export interface ExcelImport { filename: string; rows: ManualRow[]; skipped: string[] }

function toBase64(buf: ArrayBuffer): string {
  let bin = "";
  const bytes = new Uint8Array(buf);
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}

export async function importExcel(file: File): Promise<ExcelImport> {
  return request<ExcelImport>("/api/breakout15/excel", {
    method: "POST",
    body: JSON.stringify({ filename: file.name, content_base64: toBase64(await file.arrayBuffer()) }),
  });
}

function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export { saveBlob };

/** File name carries the index and the exact date range (and exit rule) of the result, so exports of
 * different ranges never share a name. */
export function exportFileName(r: Pick<Breakout15Result, "symbol" | "from" | "to" | "exit_mode">): string {
  return `${r.symbol}_${r.from}_to_${r.to}${r.exit_mode === "SECOND_LAST" ? "_exit-1515" : ""}.xlsx`;
}

export async function downloadResultXlsx(result: Breakout15Result): Promise<void> {
  const res = await fetch(`${API_BASE}/api/breakout15/export/${result.symbol}`);
  if (!res.ok) throw new Error("Export failed - run the backtest first");
  saveBlob(await res.blob(), exportFileName(result));
}
