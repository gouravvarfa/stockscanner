import type { HistoryResultRow, HistorySnapshotMeta } from "./localHistoryDb";

const COLUMNS: Array<[keyof HistoryResultRow, string]> = [
  ["symbol", "Symbol"],
  ["instrumentType", "Instrument Type"],
  ["strategy", "Strategy"],
  ["timeframe", "Timeframe"],
  ["status", "Status"],
  ["price", "Price"],
  ["rsi", "RSI"],
  ["signal", "Signal"],
  ["aDate", "A Date"],
  ["bDate", "B Date"],
  ["aPrice", "A Price"],
  ["bPrice", "B Price"],
  ["aRsi", "A RSI"],
  ["bRsi", "B RSI"],
  ["abDistance", "A-B Distance"],
  ["details", "Details"],
];

function csvCell(v: unknown): string {
  if (v === null || v === undefined) return "";
  const s = String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

/** CSV export of one local snapshot — opens directly in Excel/Sheets. No
 *  binary .xlsx writer is bundled for this (would be a new dependency for a
 *  format Excel already opens natively via CSV). */
export function exportSnapshotToCsv(meta: HistorySnapshotMeta, rows: HistoryResultRow[]): void {
  const lines = [COLUMNS.map(([, label]) => csvCell(label)).join(",")];
  for (const row of rows) {
    lines.push(COLUMNS.map(([key]) => csvCell(row[key])).join(","));
  }
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `scan-history_${meta.scanDate}_${meta.scanTime.replace(/:/g, "-")}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}
