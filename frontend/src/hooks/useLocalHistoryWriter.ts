import { useEffect, useRef } from "react";
import type { ScanResult } from "../services/api";
import type { PartialResult } from "../services/scanJobsApi";
import type { ScanJobOut } from "../services/scanJobsApi";
import {
  localIdForJob,
  mapScanResultToHistoryRows,
  newSnapshotMeta,
  partialToRow,
  summarizeStatus,
} from "../services/historyRowMapping";
import { getSnapshot, putResults, putSnapshot } from "../services/localHistoryDb";

const META_FLUSH_INTERVAL_MS = 1500; // matches useScanJob's own poll cadence — no point writing more often

/**
 * Writes the running scan's progress into the browser's permanent local
 * IndexedDB history AS IT HAPPENS (see services/localHistoryDb.ts) — never
 * waits for the scan to finish, and never re-fetches Angel One or
 * recalculates a strategy: every write is the backend's own already-computed
 * data, just persisted client-side so it survives a refresh, a browser
 * restart, or the Render instance restarting/being replaced.
 */
export function useLocalHistoryWriter(scanType: string, job: ScanJobOut | null, partial: PartialResult[], result: ScanResult | null) {
  const localIdRef = useRef<string | null>(null);
  const seenPartialSeq = useRef(0);
  const lastMetaFlush = useRef(0);
  const finalizedFor = useRef<string | null>(null);

  // New job started (or resumed on mount) -> create/resume its snapshot row.
  useEffect(() => {
    if (!job) return;
    const localId = localIdForJob(scanType, job.job_id);
    if (localIdRef.current === localId) return;
    localIdRef.current = localId;
    seenPartialSeq.current = 0;
    finalizedFor.current = null;
    getSnapshot(localId).then((existing) => {
      if (existing) return; // resumed after a refresh — keep what's already there
      putSnapshot(newSnapshotMeta(scanType, job.job_id, job.start_time, job.total)).catch(() => undefined);
    });
  }, [scanType, job]);

  // Progressive rows: only the NEW entries in `partial` since last render,
  // written immediately (each stock's chip = one write, not a re-render of
  // the whole dataset) — this is what survives a mid-scan refresh.
  useEffect(() => {
    const localId = localIdRef.current;
    if (!localId || partial.length === 0) return;
    const fresh = partial.filter((p) => p.seq > seenPartialSeq.current);
    if (fresh.length === 0) return;
    seenPartialSeq.current = Math.max(...fresh.map((p) => p.seq));
    const now = new Date().toISOString();
    const rows = fresh.flatMap((p) => p.strategies.map((strategy) => partialToRow(localId, p, strategy, now)));
    putResults(rows).catch(() => undefined);
  }, [partial]);

  // Snapshot metadata (processed/failed/signals counts), throttled — not on
  // every progress tick, so this never becomes its own render-time cost.
  useEffect(() => {
    const localId = localIdRef.current;
    if (!localId || !job) return;
    const now = Date.now();
    if (now - lastMetaFlush.current < META_FLUSH_INTERVAL_MS && job.status === "running") return;
    lastMetaFlush.current = now;
    putSnapshot({
      localId,
      scanId: null,
      jobId: job.job_id,
      scanType,
      scanDate: newSnapshotMeta(scanType, job.job_id, job.start_time, job.total).scanDate,
      scanTime: newSnapshotMeta(scanType, job.job_id, job.start_time, job.total).scanTime,
      startedAt: job.start_time,
      completedAt: job.completion_time,
      durationSeconds: job.elapsed_seconds,
      totalStocks: job.total,
      processedStocks: job.processed,
      successfulStocks: job.successful,
      failedStocks: job.failed,
      signalCount: job.signals_found,
      status: summarizeStatus(job),
    }).catch(() => undefined);
  }, [scanType, job]);

  // Scan finished with a full result -> replace the lightweight progressive
  // rows with the exact, detailed final data (A/B dates, RSI, PRD status,
  // etc.) — still purely a reformat of what the backend already computed.
  useEffect(() => {
    const localId = localIdRef.current;
    if (!localId || !job || job.status !== "completed" || !result) return;
    if (finalizedFor.current === localId) return;
    finalizedFor.current = localId;
    const rows = mapScanResultToHistoryRows(localId, result);
    // Batch in chunks so a 615-stock result never blocks the UI thread in one go.
    const CHUNK = 150;
    (async () => {
      for (let i = 0; i < rows.length; i += CHUNK) {
        await putResults(rows.slice(i, i + CHUNK));
        await new Promise((r) => setTimeout(r, 0));
      }
      await putSnapshot({
        localId,
        scanId: result.scan_id,
        jobId: job.job_id,
        scanType,
        scanDate: newSnapshotMeta(scanType, job.job_id, job.start_time, job.total).scanDate,
        scanTime: newSnapshotMeta(scanType, job.job_id, job.start_time, job.total).scanTime,
        startedAt: job.start_time,
        completedAt: job.completion_time,
        durationSeconds: job.elapsed_seconds,
        totalStocks: result.universe_requested,
        processedStocks: job.processed,
        successfulStocks: job.successful,
        failedStocks: result.stocks_failed,
        signalCount: job.signals_found,
        status: "completed",
      });
    })().catch(() => undefined);
  }, [scanType, job, result]);
}
