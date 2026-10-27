import type { Breakout15Row, ManualRow } from "./breakout15Api";

export interface CompareRow {
  date: string;
  side: ManualRow["side"];
  excelCandlePct: number | null;
  backtestCandlePct: number | null;
  candleDiff: number | null; // backtest - excel, in percentage points
  excelOutcome: ManualRow["outcome"];
  backtestSide: Breakout15Row["side"];
  backtestOutcome: "PROFIT" | "LOSS" | "NO_ENTRY" | "INCOMPLETE" | null; // null: date not in this backtest
  excelEodPct: number | null;
  backtestPnlPct: number | null;
  verdict: "MATCH" | "DIFFERENT" | "NO_DATA";
}

function backtestOutcome(r: Breakout15Row | undefined): CompareRow["backtestOutcome"] {
  if (!r) return null;
  if (r.exit_reason === "NO_ENTRY") return "NO_ENTRY";
  if (r.exit_reason.startsWith("DATA") || r.pnl_points == null) return "INCOMPLETE";
  return r.pnl_points > 0 ? "PROFIT" : "LOSS";
}

/** Compares the user's manual sheet with the backtest, by date. A day MATCHES when the backtest took the same
 * side (CALL/PUT) and ended on the same profit/loss. A both-ends ambiguous day (side BOTH) is a stop-loss
 * whichever side the sheet chose, so it matches a LOSS row. */
export function compareWithManual(manual: ManualRow[], rows: Breakout15Row[]): CompareRow[] {
  const byDate = new Map(rows.map((r) => [r.date, r]));
  return manual.map((m) => {
    const r = byDate.get(m.date);
    const outcome = backtestOutcome(r);
    const bPct = r?.first_range_pct ?? null;
    let verdict: CompareRow["verdict"];
    if (!r) verdict = "NO_DATA";
    else {
      const sideOk = r.side === "BOTH" ? true : r.side === m.side;
      verdict = sideOk && m.outcome != null && m.outcome === outcome ? "MATCH" : "DIFFERENT";
    }
    return {
      date: m.date, side: m.side, excelCandlePct: m.candle_pct, backtestCandlePct: bPct,
      candleDiff: m.candle_pct != null && bPct != null ? bPct - m.candle_pct : null,
      excelOutcome: m.outcome, backtestSide: r?.side ?? null, backtestOutcome: outcome, excelEodPct: m.eod_pct,
      backtestPnlPct: r?.pnl_pct ?? null, verdict,
    };
  });
}

export function summarizeComparison(rows: CompareRow[]) {
  const diffs = rows.flatMap((r) => (r.candleDiff == null ? [] : [Math.abs(r.candleDiff)]));
  const calls = rows.filter((r) => r.verdict === "MATCH" || r.verdict === "DIFFERENT");
  return {
    compared: rows.filter((r) => r.verdict !== "NO_DATA").length,
    noData: rows.filter((r) => r.verdict === "NO_DATA").length,
    avgCandleDiff: diffs.length ? diffs.reduce((a, b) => a + b, 0) / diffs.length : null,
    callRows: calls.length,
    callMatches: calls.filter((r) => r.verdict === "MATCH").length,
  };
}

const csvCell = (v: unknown) => {
  const t = v == null ? "" : String(v);
  return /[",\n]/.test(t) ?`"${t.replace(/"/g, '""')}"` : t;
};

export function compareToCsv(rows: CompareRow[]): string {
  const head = ["Date", "Excel side", "Backtest side", "Excel candle %", "Backtest candle %", "Diff (pts)", "Excel result", "Backtest result",
    "Excel EOD %", "Backtest P&L %", "Verdict"];
  const r2 = (v: number | null) => (v == null ? "" : Math.round(v * 100) / 100);
  const lines = [head, ...rows.map((r) => [r.date, r.side ?? "", r.backtestSide ?? "", r2(r.excelCandlePct), r2(r.backtestCandlePct), r2(r.candleDiff),
    r.excelOutcome ?? "", r.backtestOutcome ?? "no data", r2(r.excelEodPct), r2(r.backtestPnlPct), r.verdict])];
  return "﻿" + lines.map((l) => l.map(csvCell).join(",")).join("\n");
}
