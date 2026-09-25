import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ScanApiError, type ScanJobOut } from "../services/scanJobsApi";

vi.mock("../services/scanJobsApi", async () => {
  const actual = await vi.importActual<typeof import("../services/scanJobsApi")>("../services/scanJobsApi");
  return {
    ...actual,
    scanJobsApi: {
      start: vi.fn(), fresh: vi.fn(), listJobs: vi.fn(), getJob: vi.fn(), getJobResults: vi.fn(),
      getPartial: vi.fn(), getProgressLog: vi.fn(), cancelJob: vi.fn(), getCache: vi.fn(), deleteCache: vi.fn(),
    },
  };
});

vi.mock("../services/localHistoryDb", () => ({
  getLocalScanCache: vi.fn(),
  putLocalScanCache: vi.fn(),
  deleteLocalScanCache: vi.fn(),
}));

import { scanJobsApi } from "../services/scanJobsApi";
import { deleteLocalScanCache, getLocalScanCache, putLocalScanCache } from "../services/localHistoryDb";
import { useScanJob } from "./useScanJob";

const api = scanJobsApi as unknown as Record<string, ReturnType<typeof vi.fn>>;
const getLocal = getLocalScanCache as unknown as ReturnType<typeof vi.fn>;
const putLocal = putLocalScanCache as unknown as ReturnType<typeof vi.fn>;
const deleteLocal = deleteLocalScanCache as unknown as ReturnType<typeof vi.fn>;

const LOCAL = {
  scan_type: "cup_breakout", result: { results: [{ symbol: "LOCALONLY" }] },
  data_timestamp: "2026-09-25T10:00:00Z", completed_at: "2026-09-25T10:00:00Z", provider: "angel_one",
};

function job(overrides: Partial<ScanJobOut> = {}): ScanJobOut {
  return {
    job_id: "scan_x", device_id: "d", scan_type: "cup_breakout", status: "running",
    start_time: new Date().toISOString(), completion_time: null, processed: 0, total: 10, percentage: 0,
    successful: 0, failed: 0, current_symbol: null, elapsed_seconds: 0, eta_seconds: null, result_count: null,
    signals_found: 0, error: null, failed_symbols: [], ...overrides,
  };
}

async function flush() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  getLocal.mockResolvedValue(null);
  putLocal.mockResolvedValue(undefined);
  deleteLocal.mockResolvedValue(undefined);
  api.listJobs.mockResolvedValue([]);
  api.getCache.mockRejectedValue(new ScanApiError("no cache", 404));
  api.getPartial.mockResolvedValue({ items: [], next: 0, status: "running" });
  api.getProgressLog.mockResolvedValue({ items: [], next: 0, status: "running" });
});

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe("useScanJob device-local cache", () => {
  it("shows the local cache on load even while Render is down/restarting", async () => {
    getLocal.mockResolvedValue(LOCAL);
    api.listJobs.mockRejectedValue(new TypeError("Failed to fetch")); // backend unreachable
    const { result } = renderHook(() => useScanJob("cup_breakout"));
    await flush();
    expect(result.current.result).toEqual(LOCAL.result);
    expect(result.current.cache?.completed_at).toBe(LOCAL.completed_at);
  });

  it("a valid local cache means no backend download on load", async () => {
    getLocal.mockResolvedValue(LOCAL);
    renderHook(() => useScanJob("cup_breakout"));
    await flush();
    expect(api.getCache).not.toHaveBeenCalled();
    expect(api.getJobResults).not.toHaveBeenCalled();
  });

  it("a scan still running for this device takes priority over the local cache", async () => {
    getLocal.mockResolvedValue(LOCAL);
    api.listJobs.mockResolvedValue([job()]);
    api.getJob.mockResolvedValue(job());
    const { result } = renderHook(() => useScanJob("cup_breakout"));
    await flush();
    expect(result.current.running).toBe(true);
    expect(result.current.job?.job_id).toBe("scan_x");
  });

  it("cache miss: fetches from the backend, then saves a local copy", async () => {
    const backend = { ...LOCAL, result: { results: [{ symbol: "FROMRENDER" }] } };
    api.getCache.mockResolvedValue(backend);
    const { result } = renderHook(() => useScanJob("cup_breakout"));
    await flush();
    expect(result.current.result).toEqual(backend.result);
    expect(putLocal).toHaveBeenCalledWith("cup_breakout", expect.objectContaining({ result: backend.result }));
  });

  it("normal Scan uses a valid local cache without calling the backend", async () => {
    const { result } = renderHook(() => useScanJob("cup_breakout"));
    await flush();
    getLocal.mockResolvedValue(LOCAL);
    await act(async () => {
      await result.current.run();
    });
    expect(api.start).not.toHaveBeenCalled();
    expect(result.current.result).toEqual(LOCAL.result);
  });

  it("Fresh Scan invalidates the local cache before starting", async () => {
    api.fresh.mockResolvedValue({ status: "started", job: job() });
    api.getJob.mockResolvedValue(job());
    const { result } = renderHook(() => useScanJob("cup_breakout"));
    await flush();
    await act(async () => {
      await result.current.runFresh();
    });
    expect(deleteLocal).toHaveBeenCalledWith("cup_breakout");
    expect(deleteLocal.mock.invocationCallOrder[0]).toBeLessThan(api.fresh.mock.invocationCallOrder[0]);
  });

  it("a completed scan's result is saved locally", async () => {
    api.start.mockResolvedValue({ status: "started", job: job() });
    api.getJob.mockResolvedValue(job({ status: "completed", completion_time: "2026-09-25T11:00:00Z" }));
    api.getJobResults.mockResolvedValue({ results: [{ symbol: "NEW" }] });
    const { result } = renderHook(() => useScanJob("cup_breakout"));
    await flush();
    await act(async () => {
      await result.current.run();
    });
    await flush();
    expect(putLocal).toHaveBeenCalledWith(
      "cup_breakout",
      expect.objectContaining({ result: { results: [{ symbol: "NEW" }] }, completed_at: "2026-09-25T11:00:00Z" }),
    );
  });
});
