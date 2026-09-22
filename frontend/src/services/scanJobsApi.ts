import { getDeviceId } from "./deviceId";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail: string | Record<string, unknown> | undefined;
    try {
      detail = (await res.json()).detail;
    } catch {
      // not JSON
    }
    // A 409 "already running" detail is a structured {message, job_id} (see
    // backend/api/scan_jobs.py) — carry job_id through so a caller can
    // adopt/poll that exact job directly, no separate list-and-guess needed.
    const message = typeof detail === "string" ? detail : (detail?.message as string | undefined);
    const jobId = typeof detail === "object" ? (detail?.job_id as string | undefined) : undefined;
    if (res.status === 404 || res.status === 409 || res.status === 202) {
      // Callers of getJob/getCache/etc. treat these as expected states, not
      // hard errors — still throw so callers can branch on res.status via
      // ScanApiError, but keep the message informative.
      throw new ScanApiError(message ?? `${path} -> ${res.status}`, res.status, jobId);
    }
    throw new ScanApiError(message ?? `API ${path} failed: ${res.status}`, res.status, jobId);
  }
  return res.json() as Promise<T>;
}

export class ScanApiError extends Error {
  status: number;
  jobId?: string;
  constructor(message: string, status: number, jobId?: string) {
    super(message);
    this.status = status;
    this.jobId = jobId;
  }
}

export type ScanType = "a_group" | "expiry_level_1" | "expiry_level_5";
export type JobStatus = "running" | "completed" | "failed" | "cancelled";

export interface FailedSymbolOut {
  symbol: string;
  error: string;
  timestamp: string;
}

export interface ScanJobOut {
  job_id: string;
  device_id: string | null;
  scan_type: ScanType;
  status: JobStatus;
  start_time: string;
  completion_time: string | null;
  processed: number;
  total: number;
  percentage: number;
  successful: number;
  failed: number;
  current_symbol: string | null;
  elapsed_seconds: number;
  eta_seconds: number | null;
  result_count: number | null;
  signals_found: number;
  error: string | null;
  failed_symbols: FailedSymbolOut[];
}

/** Full detail for one qualifying strategy signal on a stock — a straight
 *  reformat of what the backend already computed (see
 *  backend/services/scan_job_manager.py::record_result). Same fields as
 *  StrategySignal (services/api.ts), minus `conditions`. */
export interface PartialSignal {
  strategy: string;
  symbol: string;
  instrument_type: "FUTURE" | "EQUITY" | null;
  qualifies: boolean;
  daily_rsi: number | null;
  weekly_rsi: number | null;
  monthly_rsi: number | null;
  explanation: string;
  extra: Record<string, unknown>;
}

export interface PartialResult {
  seq: number;
  symbol: string;
  instrument_type: "FUTURE" | "EQUITY";
  strategies: string[];
  signals: PartialSignal[];
}

export interface PartialOut {
  items: PartialResult[];
  next: number;
  status: JobStatus;
}

/** One processed stock (success or fail) — every stock, not just qualifying
 *  ones. See GET /jobs/{id}/progress. */
export interface ProgressLogItem {
  seq: number;
  symbol: string;
  instrument_type: "FUTURE" | "EQUITY";
  success: boolean;
  error: string | null;
}

export interface ProgressLogOut {
  items: ProgressLogItem[];
  next: number;
  status: JobStatus;
}

export interface CacheEnvelope<T = unknown> {
  scan_type: ScanType;
  result: T;
  data_timestamp: string;
  completed_at: string;
  provider: string;
}

export type StartScanResponse<T = unknown> =
  | { status: "cached"; cache: CacheEnvelope<T> }
  | { status: "started"; job: ScanJobOut };

export const scanJobsApi = {
  // device_id scopes which browser SEES/controls a job afterwards — see
  // services/deviceId.ts. The scan itself still runs once, server-side,
  // regardless of which device started it.
  start: <T = unknown>(scanType: ScanType) =>
    request<StartScanResponse<T>>("/api/scan/start", {
      method: "POST",
      body: JSON.stringify({ scan_type: scanType, device_id: getDeviceId() }),
    }),

  fresh: <T = unknown>(scanType: ScanType) =>
    request<StartScanResponse<T>>("/api/scan/fresh", {
      method: "POST",
      body: JSON.stringify({ scan_type: scanType, device_id: getDeviceId() }),
    }),

  listJobs: () => request<ScanJobOut[]>(`/api/scan/jobs?device_id=${encodeURIComponent(getDeviceId())}`),

  getJob: (jobId: string) => request<ScanJobOut>(`/api/scan/jobs/${jobId}?device_id=${encodeURIComponent(getDeviceId())}`),

  getJobResults: <T = unknown>(jobId: string) => request<T>(`/api/scan/jobs/${jobId}/results`),

  getPartial: (jobId: string, after: number) => request<PartialOut>(`/api/scan/jobs/${jobId}/partial?after=${after}`),

  getProgressLog: (jobId: string, after: number) =>
    request<ProgressLogOut>(`/api/scan/jobs/${jobId}/progress?after=${after}`),

  cancelJob: (jobId: string) =>
    request<{ status: string }>(`/api/scan/jobs/${jobId}/cancel?device_id=${encodeURIComponent(getDeviceId())}`, {
      method: "POST",
    }),

  getCache: <T = unknown>(scanType: ScanType) => request<CacheEnvelope<T>>(`/api/scan/cache/${scanType}`),

  deleteCache: (scanType: ScanType) =>
    request<{ status: string }>(`/api/scan/cache/${scanType}`, { method: "DELETE" }),
};

export function fmtDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return "—";
  const s = Math.max(0, Math.round(seconds));
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${String(m).padStart(2, "0")}:${String(rem).padStart(2, "0")}`;
}

export function scanTypeLabel(scanType: ScanType): string {
  switch (scanType) {
    case "a_group":
      return "A Group Scanner";
    case "expiry_level_1":
      return "Expiry Level 1";
    case "expiry_level_5":
      return "Expiry Level 5";
  }
}
