import type { NiftyUniverseStock, ScanResult } from "./api";
import { resultRowKey, type HistoryResultRow, type HistorySnapshotMeta, type SnapshotStatus } from "./localHistoryDb";
import type { PartialResult, PartialSignal, ProgressLogItem } from "./scanJobsApi";

const IST_OFFSET_MINUTES = 5.5 * 60;

function toIst(date: Date): Date {
  const utcMs = date.getTime() + date.getTimezoneOffset() * 60000;
  return new Date(utcMs + IST_OFFSET_MINUTES * 60000);
}

export function istDateKey(isoOrDate: string | Date): string {
  const d = toIst(typeof isoOrDate === "string" ? new Date(isoOrDate) : isoOrDate);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function istTimeKey(isoOrDate: string | Date): string {
  const d = toIst(typeof isoOrDate === "string" ? new Date(isoOrDate) : isoOrDate);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:${String(d.getSeconds()).padStart(2, "0")}`;
}

/** Local snapshot key: stable across the whole run of one scan job — every
 *  progressive write and the final completion write target the same row. */
export function localIdForJob(scanType: string, jobId: string): string {
  return `${scanType}:job:${jobId}`;
}

export function newSnapshotMeta(
  scanType: string,
  jobId: string,
  startedAtIso: string,
  totalStocks: number,
): HistorySnapshotMeta {
  return {
    localId: localIdForJob(scanType, jobId),
    scanId: null,
    jobId,
    scanType,
    scanDate: istDateKey(startedAtIso),
    scanTime: istTimeKey(startedAtIso),
    startedAt: startedAtIso,
    completedAt: null,
    durationSeconds: null,
    totalStocks,
    processedStocks: 0,
    successfulStocks: 0,
    failedStocks: 0,
    signalCount: 0,
    status: "running",
  };
}

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}
function str(v: unknown): string | null {
  return v === null || v === undefined ? null : String(v).slice(0, 10);
}

/** A DATA_UNAVAILABLE (failed) or SCANNED_NO_SIGNAL row for one stock, from
 *  the all-stocks progress stream (GET /jobs/{id}/progress) — persisted the
 *  moment that stock finishes, whether or not it qualified for anything, so
 *  a mid-scan interruption still leaves a complete, gap-free local record. */
export function mapProgressItemToRow(localId: string, item: ProgressLogItem): HistoryResultRow {
  const now = new Date().toISOString();
  const row: HistoryResultRow = {
    id: "",
    localId,
    symbol: item.symbol,
    instrumentType: item.instrument_type,
    strategy: "",
    timeframe: null,
    status: item.success ? "SCANNED_NO_SIGNAL" : "DATA_UNAVAILABLE",
    price: null,
    rsi: null,
    signal: null,
    aDate: null,
    bDate: null,
    aPrice: null,
    bPrice: null,
    aRsi: null,
    bRsi: null,
    abDistance: null,
    details: item.error ?? "",
    createdAt: now,
    updatedAt: now,
  };
  row.id = resultRowKey(row);
  return row;
}

/** Minimal shape both StrategySignal (services/api.ts) and PartialSignal
 *  (services/scanJobsApi.ts, the live per-stock stream) satisfy — the same
 *  mapping logic below works for a signal read from the FINAL result or
 *  from the live stream the moment that stock finishes, without waiting
 *  for the scan to complete. */
interface SignalLike {
  symbol: string;
  instrument_type?: "FUTURE" | "EQUITY" | null;
  daily_rsi: number | null;
  weekly_rsi: number | null;
  monthly_rsi: number | null;
  explanation: string;
  extra: Record<string, unknown>;
}

/** Full, accurate rows straight from the backend's own already-computed
 *  data — never recalculated here, only reformatted (mirrors
 *  backend/services/excel_sync/rows.py's PRD/PRD-Forming field mapping).
 *  Used both for the live per-stock stream (as soon as a stock qualifies)
 *  and for the final ScanResult (mapScanResultToHistoryRows below). */
export function signalToRows(
  localId: string,
  strategyName: string,
  signal: SignalLike,
  instrumentType: "FUTURE" | "EQUITY" | null,
  now: string,
): HistoryResultRow[] {
  const extra = signal.extra ?? {};
  const price = num(extra.current_price);
  const base = (): HistoryResultRow => {
    const row: HistoryResultRow = {
      id: "",
      localId,
      symbol: signal.symbol,
      instrumentType: signal.instrument_type ?? instrumentType,
      strategy: strategyName,
      timeframe: null,
      status: "QUALIFIED",
      price,
      rsi: signal.weekly_rsi ?? signal.daily_rsi ?? null,
      signal: "QUALIFIED",
      aDate: null,
      bDate: null,
      aPrice: null,
      bPrice: null,
      aRsi: null,
      bRsi: null,
      abDistance: null,
      details: (signal.explanation ?? "").slice(0, 400),
      createdAt: now,
      updatedAt: now,
    };
    return row;
  };
  const withId = (row: HistoryResultRow): HistoryResultRow => ({ ...row, id: resultRowKey(row) });

  if (strategyName === "PRD Forming") {
    const forming = Array.isArray(extra.forming) ? (extra.forming as Record<string, unknown>[]) : [];
    return forming.map((f) =>
      withId({
        ...base(),
        timeframe: str(f.timeframe)?.toUpperCase() ?? null,
        status: "PRD_FORMING",
        signal: "PRD_FORMING",
        rsi: num(f.b_rsi),
        aDate: str(f.a_date),
        bDate: str(f.b_date),
        aPrice: num(f.a_low),
        bPrice: num(f.b_low),
        aRsi: num(f.a_rsi),
        bRsi: num(f.b_rsi),
        abDistance: typeof f.ab_distance === "number" ? f.ab_distance : null,
      }),
    );
  }

  if ((strategyName === "PRD" || strategyName === "NRD") && Array.isArray(extra.divergences) && extra.divergences.length) {
    const status = typeof extra.status === "string" ? extra.status : "QUALIFIED";
    return (extra.divergences as Record<string, unknown>[]).map((d) =>
      withId({
        ...base(),
        timeframe: str(d.timeframe)?.toUpperCase() ?? null,
        status,
        signal: status,
        rsi: num(d.b_rsi ?? d.rsi2),
        aDate: str(d.a_date ?? d.swing1_date),
        bDate: str(d.b_date ?? d.swing2_date),
        aPrice: num(d.a_low ?? d.swing1_price),
        bPrice: num(d.b_low ?? d.swing2_price),
        aRsi: num(d.a_rsi ?? d.rsi1),
        bRsi: num(d.b_rsi ?? d.rsi2),
        abDistance:
          typeof d.ab_distance === "number"
            ? d.ab_distance
            : typeof d.swing1_bar === "number" && typeof d.swing2_bar === "number"
              ? (d.swing2_bar as number) - (d.swing1_bar as number)
              : null,
      }),
    );
  }

  return [withId(base())];
}

/** Full rows the moment ONE stock's qualifying signals arrive via the live
 *  `/partial` stream — written immediately, not just at scan completion. */
export function mapPartialSignalsToRows(localId: string, partial: PartialResult): HistoryResultRow[] {
  const now = new Date().toISOString();
  return (partial.signals as PartialSignal[]).flatMap((s) =>
    signalToRows(localId, s.strategy, s, s.instrument_type ?? partial.instrument_type, now),
  );
}

/** Full, accurate rows for every stock in a COMPLETED scan's final result —
 *  used to fill in anything the live streams above might have missed (e.g.
 *  if this browser tab wasn't open for part of the scan) and to write the
 *  final failed-stock rows. Never recalculated — only reformatted. */
export function mapScanResultToHistoryRows(localId: string, result: ScanResult): HistoryResultRow[] {
  const now = new Date().toISOString();
  const rows: HistoryResultRow[] = [];
  const instrumentBySymbol = new Map<string, "FUTURE" | "EQUITY" | null>();
  for (const u of result.nifty200_universe as NiftyUniverseStock[]) {
    instrumentBySymbol.set(u.symbol, u.instrument_type ?? null);
    if (u.status !== "OK") {
      const row: HistoryResultRow = {
        id: "",
        localId,
        symbol: u.symbol,
        instrumentType: u.instrument_type ?? null,
        strategy: "",
        timeframe: null,
        status: "DATA_UNAVAILABLE",
        price: null,
        rsi: null,
        signal: null,
        aDate: null,
        bDate: null,
        aPrice: null,
        bPrice: null,
        aRsi: null,
        bRsi: null,
        abDistance: null,
        details: u.status_reason ?? "",
        createdAt: now,
        updatedAt: now,
      };
      row.id = resultRowKey(row);
      rows.push(row);
    }
  }

  for (const [strategyName, signals] of Object.entries(result.strategies ?? {})) {
    for (const signal of signals) {
      rows.push(...signalToRows(localId, strategyName, signal, instrumentBySymbol.get(signal.symbol) ?? null, now));
    }
  }
  return rows;
}

export function summarizeStatus(job: { status: string } | null | undefined): SnapshotStatus {
  switch (job?.status) {
    case "completed":
      return "completed";
    case "cancelled":
      return "stopped";
    case "failed":
      return "failed";
    default:
      return "running";
  }
}
