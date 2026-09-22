import { getDeviceId } from "./deviceId";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail: string | undefined;
    try {
      detail = (await res.json()).detail;
    } catch {
      // not JSON
    }
    if (res.status === 404 || res.status === 409 || res.status === 202) {
      // Callers of getJob/getCache/etc. treat these as expected states, not
      // hard errors — still throw so callers can branch on res.status via
      // ScanApiError, but keep the message informative.
      throw new ScanApiError(detail ?? `${path} -> ${res.status}`, res.status);
    }
    throw new ScanApiError(detail ?? `API ${path} failed: ${res.status}`, res.status);
  }
  return res.json() as Promise<T>;
}

export class ScanApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
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

export interface PartialResult {
  seq: number;
  symbol: string;
  instrument_type: "FUTURE" | "EQUITY";
  strategies: string[];
}

export interface PartialOut {
  items: PartialResult[];
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
