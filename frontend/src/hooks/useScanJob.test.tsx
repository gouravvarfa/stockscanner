import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ScanApiError, type ScanJobOut } from "../services/scanJobsApi";

// Mock the API layer only — real ScanApiError class is reused so the
// hook's `instanceof ScanApiError` checks behave exactly as in production.
vi.mock("../services/scanJobsApi", async () => {
  const actual = await vi.importActual<typeof import("../services/scanJobsApi")>("../services/scanJobsApi");
  return {
    ...actual,
    scanJobsApi: {
      start: vi.fn(),
      fresh: vi.fn(),
      listJobs: vi.fn(),
      getJob: vi.fn(),
      getJobResults: vi.fn(),
      getPartial: vi.fn(),
      getProgressLog: vi.fn(),
      cancelJob: vi.fn(),
      getCache: vi.fn(),
      deleteCache: vi.fn(),
    },
  };
});

import { scanJobsApi } from "../services/scanJobsApi";
import { useScanJob } from "./useScanJob";

const api = scanJobsApi as unknown as Record<string, ReturnType<typeof vi.fn>>;

function job(overrides: Partial<ScanJobOut> = {}): ScanJobOut {
  return {
    job_id: "scan_test1",
    device_id: "device-1",
    scan_type: "a_group",
    status: "running",
    start_time: new Date().toISOString(),
    completion_time: null,
    processed: 10,
    total: 615,
    percentage: 1.6,
    successful: 10,
    failed: 0,
    current_symbol: "RELIANCE",
    elapsed_seconds: 5,
    eta_seconds: null,
    result_count: null,
    signals_found: 0,
    error: null,
    failed_symbols: [],
    ...overrides,
  };
}

async function flush() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  api.listJobs.mockResolvedValue([]);
  api.getCache.mockRejectedValue(new ScanApiError("no cache", 404));
  // Realistic default: echoes back a "still running" job for whatever id
  // was asked — individual tests override with mockResolvedValueOnce /
  // mockRejectedValueOnce for the specific tick(s) they care about.
  api.getJob.mockImplementation((jobId: string) => Promise.resolve(job({ job_id: jobId })));
  api.getPartial.mockResolvedValue({ items: [], next: 0, status: "running" });
  api.getProgressLog.mockResolvedValue({ items: [], next: 0, status: "running" });
});

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

async function startScan() {
  api.start.mockResolvedValueOnce({ status: "started", job: job() });
  const view = renderHook(() => useScanJob("a_group"));
  await act(async () => {
    await view.result.current.run();
  });
  await flush(); // let the first poll tick (fired inside run()) settle
  return view;
}

describe("useScanJob — restart/outage handling", () => {
  it("existing active scan continues to display correctly when backend is healthy", async () => {
    const view = await startScan();
    expect(view.result.current.running).toBe(true);

    api.getJob.mockResolvedValueOnce(job({ processed: 20, percentage: 3.2 }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
    });
    expect(view.result.current.job?.processed).toBe(20);
    expect(view.result.current.running).toBe(true);
    expect(view.result.current.error).toBeNull();
  });

  it("recovers from a temporary 30-40s backend outage without losing the running job", async () => {
    const view = await startScan();

    // Every poll fails for ~36s (backend unreachable mid-restart), then recovers.
    api.getJob.mockRejectedValue(new TypeError("Failed to fetch"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(36_000);
    });

    // Still shows as running/retrying, not a hard failure — recovery window (60s) not exhausted.
    expect(view.result.current.running).toBe(true);
    expect(view.result.current.issueKind).toBe("unavailable");
    expect(api.start).toHaveBeenCalledTimes(1); // no duplicate scan auto-started during the outage

    // Backend comes back.
    api.getJob.mockReset();
    api.getJob.mockResolvedValue(job({ processed: 50 }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(8000);
    });
    expect(view.result.current.job?.processed).toBe(50);
    expect(view.result.current.issueKind).toBeNull();
    expect(view.result.current.error).toBeNull();
  }, 15000);

  it("detects a job that disappeared after a restart and stops immediately (no infinite retry)", async () => {
    const view = await startScan();

    api.getJob.mockRejectedValueOnce(new ScanApiError("No such job 'scan_test1'.", 404));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
    });

    expect(view.result.current.running).toBe(false);
    expect(view.result.current.job).toBeNull();
    expect(view.result.current.issueKind).toBe("interrupted");
    expect(view.result.current.error).toBe("Backend restarted — previous scan was interrupted.");

    // No further polling — getJob wasn't called again.
    const callsAfterInterrupt = api.getJob.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(api.getJob.mock.calls.length).toBe(callsAfterInterrupt);
  });

  it("Run Scan is available again right after an interrupted job is detected, with no duplicate auto-start", async () => {
    const view = await startScan();
    api.getJob.mockRejectedValueOnce(new ScanApiError("No such job 'scan_test1'.", 404));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
    });

    expect(view.result.current.running).toBe(false); // Dashboard's Run Scan button is disabled only while `scanning` (=running)
    expect(api.start).toHaveBeenCalledTimes(1); // interruption itself never auto-starts a new scan

    api.start.mockResolvedValueOnce({ status: "started", job: job({ job_id: "scan_new" }) });
    await act(async () => {
      await view.result.current.run();
    });
    await flush();
    expect(view.result.current.running).toBe(true);
    expect(view.result.current.job?.job_id).toBe("scan_new");
    expect(api.start).toHaveBeenCalledTimes(2); // the original + this explicit, user-triggered one only
  });

  it("gives up after the recovery window is exhausted — no infinite retry", async () => {
    const view = await startScan();
    api.getJob.mockRejectedValue(new TypeError("Failed to fetch"));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(65_000);
    });

    expect(view.result.current.running).toBe(false);
    expect(view.result.current.issueKind).toBe("unavailable");

    const callsAtGiveUp = api.getJob.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(api.getJob.mock.calls.length).toBe(callsAtGiveUp); // stopped polling, not stuck retrying forever
  }, 15000);

  it("uses backoff, not a tight fixed interval, while retrying an outage", async () => {
    await startScan();
    api.getJob.mockRejectedValue(new TypeError("Failed to fetch"));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500); // first retry attempt fires at the normal poll interval
    });
    const callsAfterFirst = api.getJob.mock.calls.length;
    expect(callsAfterFirst).toBeGreaterThanOrEqual(1);

    // A second failure should NOT retry again after only another 1500ms —
    // backoff must have grown past the plain poll interval by now.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
    });
    expect(api.getJob.mock.calls.length).toBe(callsAfterFirst); // no new call yet — still backing off
  });

  it("polling the same already-running job twice never duplicates partial/progress chips", async () => {
    // Simulates the exact real bug: the mount-time restore already started
    // polling job scan_test1, and something else (e.g. a 409-adopt from a
    // manual Run Scan click) calls run() again for the SAME job.
    const view = await startScan();
    // Cursor-aware, like the real backend's partial_after(after): the one
    // item is only returned once, to whichever caller asks with after=0.
    api.getPartial.mockImplementation((_jobId: string, after: number) =>
      Promise.resolve(
        after === 0
          ? { items: [{ seq: 1, symbol: "AJANTPHARM", instrument_type: "EQUITY", strategies: ["PRD Forming"], signals: [] }], next: 1, status: "running" }
          : { items: [], next: after, status: "running" },
      ),
    );
    api.getJob.mockResolvedValue(job({ signals_found: 1 }));

    // First tick appends the one item.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
    });
    expect(view.result.current.partial).toHaveLength(1);

    // Now start() gets a 409 with the SAME job_id and re-adopts it — this
    // used to spin up a SECOND concurrent poll loop for the same job.
    api.start.mockRejectedValueOnce(new ScanApiError("already running", 409, "scan_test1"));
    await act(async () => {
      await view.result.current.run();
    });
    await flush();

    // Only the latest poll loop should still be feeding `partial` — advance
    // enough ticks that a duplicate loop (if one existed) would have
    // appended the same item again.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500 * 3);
    });
    expect(view.result.current.partial.filter((p) => p.symbol === "AJANTPHARM")).toHaveLength(1);
  });
});
