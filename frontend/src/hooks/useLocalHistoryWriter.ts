import { useEffect, useRef } from "react";
import type { ScanResult } from "../services/api";
import type { PartialResult, ProgressLogItem, ScanJobOut } from "../services/scanJobsApi";
import {
  localIdForJob,
  mapPartialSignalsToRows,
  mapProgressItemToRow,
  mapScanResultToHistoryRows,
  newSnapshotMeta,
  summarizeStatus,
} from "../services/historyRowMapping";
import { getSnapshot, putResults, putSnapshot } from "../services/localHistoryDb";

const META_FLUSH_INTERVAL_MS = 1500; // matches useScanJob's own poll cadence — no point writing more often

/**
 * Writes the running scan's progress into the browser's permanent local
 * IndexedDB history AS IT HAPPENS (see services/localHistoryDb.ts) — this
 * is the primary, device-local source of truth for completed scan
 * results/history (2026-09-22 architecture decision). Render/the scan job
 * manager stays responsible only for running the scan and streaming
 * results; it never accumulates the full 615-stock dataset for this
 * purpose. Every write here is a straight reformat of data the backend
 * already computed — never re-fetches Angel One, never recalculates a
 * strategy.
 *
 * Two live streams feed this, both cursor-based (see useScanJob.ts):
 *   - `partial`: full-detail rows for stocks that QUALIFIED for >=1 strategy
 *     (A/B dates, RSI, PRD/PRD Forming status — everything, immediately).
 *   - `progressLog`: EVERY processed stock, success or fail — so a stock
 *     that scanned cleanly with no signal, or failed, is also recorded
 *     (DATA_UNAVAILABLE / SCANNED_NO_SIGNAL) the moment it finishes, not
 *     just the qualifying ones.
 * Rows are written with a deterministic key (services/localHistoryDb.ts
 * resultRowKey) — re-processing the same stream item again (e.g. after a
 * refresh replays from a fresh cursor) upserts the same row instead of
 * duplicating it.
 */
export function useLocalHistoryWriter(
  scanType: string,
  job: ScanJobOut | null,
  partial: PartialResult[],
  progressLog: ProgressLogItem[],
  result: ScanResult | null,
) {
  const localIdRef = useRef<string | null>(null);
  const seenPartialSeq = useRef(0);
  const seenProgressSeq = useRef(0);
  const lastMetaFlush = useRef(0);
  const finalizedFor = useRef<string | null>(null);

  // New job started (or resumed on mount) -> create/resume its snapshot row.
  useEffect(() => {
    if (!job) return;
    const localId = localIdForJob(scanType, job.job_id);
    if (localIdRef.current === localId) return;
    localIdRef.current = localId;
    seenPartialSeq.current = 0;
    seenProgressSeq.current = 0;
    finalizedFor.current = null;
    getSnapshot(localId).then((existing) => {
      if (existing) return; // resumed after a refresh — keep what's already there
      putSnapshot(newSnapshotMeta(scanType, job.job_id, job.start_time, job.total)).catch(() => undefined);
    });
  }, [scanType, job]);

  // Full-detail rows for stocks that qualified — only the NEW entries in
  // `partial` since last render, written immediately.
  useEffect(() => {
    const localId = localIdRef.current;
    if (!localId || partial.length === 0) return;
    const fresh = partial.filter((p) => p.seq > seenPartialSeq.current);
    if (fresh.length === 0) return;
    seenPartialSeq.current = Math.max(...fresh.map((p) => p.seq));
    const rows = fresh.flatMap((p) => mapPartialSignalsToRows(localId, p));
    putResults(rows).catch(() => undefined);
  }, [partial]);

  // DATA_UNAVAILABLE / SCANNED_NO_SIGNAL rows for EVERY other processed
  // stock — same idea, from the all-stocks progress stream.
  useEffect(() => {
    const localId = localIdRef.current;
    if (!localId || progressLog.length === 0) return;
    const fresh = progressLog.filter((p) => p.seq > seenProgressSeq.current);
    if (fresh.length === 0) return;
    seenProgressSeq.current = Math.max(...fresh.map((p) => p.seq));
    const rows = fresh.map((p) => mapProgressItemToRow(localId, p));
    putResults(rows).catch(() => undefined);
  }, [progressLog]);

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

  // Scan finished with a full result -> fill in anything the live streams
  // above might have missed (e.g. this tab wasn't open for part of the
  // scan) with the exact, detailed final data — still purely a reformat,
  // and idempotent (same deterministic keys) with what was already written.
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
