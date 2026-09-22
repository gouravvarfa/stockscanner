import type { NiftyUniverseStock, ScanResult, StrategySignal } from "./api";
import type { HistoryResultRow, HistorySnapshotMeta, SnapshotStatus } from "./localHistoryDb";
import type { PartialResult } from "./scanJobsApi";

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

/** Lightweight row from the live `partial` stream (see useScanJob) — written
 *  immediately as each stock finishes, so a mid-scan refresh loses nothing.
 *  Enriched later (same localId+symbol+strategy key) once the scan
 *  completes and the full detailed result is available. */
export function partialToRow(localId: string, p: PartialResult, strategy: string, now: string): HistoryResultRow {
  return {
    localId,
    symbol: p.symbol,
    instrumentType: p.instrument_type,
    strategy,
    timeframe: null,
    status: "QUALIFIED",
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
    details: "",
    createdAt: now,
    updatedAt: now,
  };
}

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}
function str(v: unknown): string | null {
  return v === null || v === undefined ? null : String(v).slice(0, 10);
}

/** Full, accurate rows straight from the backend's own already-computed
 *  result — never recalculated here, only reformatted (mirrors
 *  backend/services/excel_sync/rows.py's PRD/PRD-Forming field mapping). */
export function mapScanResultToHistoryRows(localId: string, result: ScanResult): HistoryResultRow[] {
  const now = new Date().toISOString();
  const rows: HistoryResultRow[] = [];
  const instrumentBySymbol = new Map<string, "FUTURE" | "EQUITY" | null>();
  for (const u of result.nifty200_universe as NiftyUniverseStock[]) {
    instrumentBySymbol.set(u.symbol, u.instrument_type ?? null);
    if (u.status !== "OK") {
      rows.push({
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
      });
    }
  }

  for (const [strategyName, signals] of Object.entries(result.strategies ?? {})) {
    for (const signal of signals as StrategySignal[]) {
      rows.push(...signalToRows(localId, strategyName, signal, instrumentBySymbol.get(signal.symbol) ?? null, now));
    }
  }
  return rows;
}

function signalToRows(
  localId: string,
  strategyName: string,
  signal: StrategySignal,
  instrumentType: "FUTURE" | "EQUITY" | null,
  now: string,
): HistoryResultRow[] {
  const extra = signal.extra ?? {};
  const price = num(extra.current_price);
  const base = (): HistoryResultRow => ({
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
  });

  if (strategyName === "PRD Forming") {
    const forming = Array.isArray(extra.forming) ? (extra.forming as Record<string, unknown>[]) : [];
    return forming.map((f) => ({
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
    }));
  }

  if ((strategyName === "PRD" || strategyName === "NRD") && Array.isArray(extra.divergences) && extra.divergences.length) {
    const status = typeof extra.status === "string" ? extra.status : "QUALIFIED";
    return (extra.divergences as Record<string, unknown>[]).map((d) => ({
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
    }));
  }

  return [base()];
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
