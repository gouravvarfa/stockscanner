import { useCallback, useEffect, useState } from "react";
import {
  breakout15Api, downloadResultXlsx, importExcel, saveBlob, type Breakout15ExitMode, type Breakout15Result, type Breakout15Row, type Breakout15Symbol, type ExcelImport,
} from "../services/breakout15Api";
import { compareToCsv, compareWithManual, summarizeComparison } from "../services/breakout15Compare";

/**
 * 15-Minute Candle Breakout (CALL) — a standalone historical index-point
 * backtest on real Angel One 15-minute candles. Separate from every other
 * strategy; nothing here places an order.
 */

const num = (v: number | null | undefined, d = 2) =>
  v == null ? "—" : v.toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d });
const pct = (v: number | null | undefined) => (v == null ? "—" : `${num(v)}%`);
const hm = (s: string | null) => (s ? s.slice(11, 16) : "—");
const tone = (v: number | null | undefined) => (v == null || v === 0 ? "" : v > 0 ? "text-success" : "text-danger");
const iso = (d: Date) => d.toISOString().slice(0, 10);
const isIncomplete = (r: Breakout15Row) => r.exit_reason.startsWith("DATA");
const sideTone = (s: Breakout15Row["side"]) => (s === "CALL" ? "text-success" : s === "PUT" ? "text-danger" : "");
const isAmbiguous = (r: Breakout15Row) => r.flags.some((f) => f.startsWith("AMBIGUOUS"));

export function Breakout15Page() {
  const [symbol, setSymbol] = useState<Breakout15Symbol>("NIFTY");
  const [from, setFrom] = useState(() => iso(new Date(Date.now() - 91 * 864e5)));
  const [to, setTo] = useState(() => iso(new Date(Date.now() - 864e5)));
  const [exitMode, setExitMode] = useState<Breakout15ExitMode>("CLOSE");
  const [result, setResult] = useState<Breakout15Result | null>(null);
  const [progress, setProgress] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [manual, setManual] = useState<ExcelImport | null>(null);

  async function onExcel(file: File | undefined) {
    if (!file) return;
    setError(null);
    try {
      setManual(await importExcel(file));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Excel import failed");
    }
  }

  const load = useCallback(async (sym: Breakout15Symbol) => {
    try {
      setResult(await breakout15Api.result(sym));
    } catch {
      setResult(null); // no run yet for this index
    }
  }, []);

  useEffect(() => { void load(symbol); }, [symbol, load]);

  async function run() {
    setError(null);
    setProgress("Starting…");
    try {
      let job = await breakout15Api.start(symbol, from, to, exitMode);
      while (job.state === "running") {
        setProgress(job.phase === "resolving"
          ? `Ordering both-ends days on 1-minute candles… ${job.done}/${job.total}`
          : `Downloading 15-minute data… ${job.done}/${job.total || "?"}`);
        await new Promise((r) => setTimeout(r, 1500));
        job = await breakout15Api.job(job.id);
      }
      if (job.state === "error") throw new Error(job.error ?? "Backtest failed");
      await load(symbol);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Backtest failed");
    } finally {
      setProgress(null);
    }
  }

  const s = result?.summary;
  const stats: [string, string, string?][] = s
    ? [
        ["Trading days", String(s.trading_days)],
        ["CALL entries", String(s.call_entries)],
        ["PUT entries", String(s.put_entries)],
        ["No-entry days", String(s.no_entry_days)],
        ["Stop-loss exits", String(s.stop_loss_exits)],
        ["Market-close exits", String(s.market_close_exits)],
        ["Incomplete-data days", String(s.incomplete_days)],
        ["Both-ends days (ordered on 1-min)", `${s.resolved_days}${s.both_side_days ? ` · ${s.both_side_days} unresolved` : ""}`],
        ["Ambiguous days", String(s.ambiguous_days)],
        ["Winning / losing", `${s.winning_trades} / ${s.losing_trades}`],
        ["Win rate", s.win_rate == null ? "—" : `${s.win_rate}%`],
        ["Net points", num(s.net_points), tone(s.net_points)],
        ["Avg points / trade", num(s.avg_points)],
        ["Max drawdown (pts)", num(s.max_drawdown_points)],
      ]
    : [];

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">15-Min Candle Breakout</h1>
          <p className="page-subtitle">
            CALL above the first 15-minute candle High (stop at its Low) · PUT below its Low (stop at its High) · first break of the day only · index points only, no orders
          </p>
        </div>
      </div>

      <div className="card filters-row filter-panel" style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
        <label className="muted small" style={{ display: "grid", gap: 4 }}>
          Index
          <select value={symbol} onChange={(e) => setSymbol(e.target.value as Breakout15Symbol)} disabled={progress !== null}>
            <option value="NIFTY">NIFTY 50</option>
            <option value="BANKNIFTY">BANK NIFTY</option>
          </select>
        </label>
        <label className="muted small" style={{ display: "grid", gap: 4 }}>
          Exit at
          <select value={exitMode} onChange={(e) => setExitMode(e.target.value as Breakout15ExitMode)} disabled={progress !== null}>
            <option value="CLOSE">15:30 close (last candle)</option>
            <option value="SECOND_LAST">15:15 (second-last candle close)</option>
          </select>
        </label>
        <label className="muted small" style={{ display: "grid", gap: 4 }}>
          From
          <input type="date" value={from} max={to} onChange={(e) => setFrom(e.target.value)} />
        </label>
        <label className="muted small" style={{ display: "grid", gap: 4 }}>
          To
          <input type="date" value={to} min={from} max={iso(new Date(Date.now() - 864e5))} onChange={(e) => setTo(e.target.value)} />
        </label>
        <button className="primary-button" onClick={run} disabled={progress !== null}>Run backtest</button>
        <label className="secondary-button" style={{ cursor: "pointer" }}>
          Import Excel (manual sheet)
          <input type="file" accept=".xlsx" style={{ display: "none" }} onChange={(e) => { void onExcel(e.target.files?.[0]); e.target.value = ""; }} />
        </label>
        <button className="secondary-button" disabled={!result || progress !== null}
          onClick={() => void (result ? downloadResultXlsx(result) : Promise.reject(new Error("Run the backtest first"))).catch((e) => setError(e instanceof Error ? e.message : "Export failed"))}>
          Export Excel
        </button>
        {progress && <span className="muted small">{progress}</span>}
      </div>

      {error && <div className="card state-block"><div className="state-title">{error}</div></div>}

      {result && s ? (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 12, margin: "16px 0" }}>
            {stats.map(([label, value, cls]) => (
              <div className="card" key={label}>
                <div className="summary-label">{label}</div>
                <div className={`summary-value ${cls ?? ""}`}>{value}</div>
              </div>
            ))}
          </div>
          <p className="muted small">
            {result.symbol} · token {result.token} · {result.from} → {result.to} · exit {result.exit_mode === "SECOND_LAST" ? "15:15" : "15:30"} · generated {result.generated_at.replace("T", " ")}
          </p>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th className="num-cell">1st Open</th><th className="num-cell">1st High</th>
                  <th className="num-cell">1st Low</th><th className="num-cell">1st Close</th>
                  <th className="num-cell">Range %</th><th>Direction</th>
                  <th>Side</th><th>Breakout</th><th className="num-cell">Entry</th><th className="num-cell">Stop loss</th>
                  <th>2nd-last</th><th className="num-cell">2nd-last close</th><th className="num-cell">2nd-last %</th>
                  <th>Exit time</th><th className="num-cell">Exit</th><th>Exit reason</th>
                  <th className="num-cell">P&amp;L pts</th><th className="num-cell">P&amp;L %</th><th>Data quality</th>
                </tr>
              </thead>
              <tbody>
                {result.rows.map((r) => (
                  <tr key={r.date} style={isAmbiguous(r) ? { background: "var(--warning-soft)" } : isIncomplete(r) ? { opacity: 0.6 } : undefined}>
                    <td>{r.date}</td>
                    <td className="num-cell">{num(r.first_open)}</td><td className="num-cell">{num(r.first_high)}</td>
                    <td className="num-cell">{num(r.first_low)}</td><td className="num-cell">{num(r.first_close)}</td>
                    <td className="num-cell">{pct(r.first_range_pct)}</td>
                    <td className={r.first_direction === "Green" ? "text-success" : r.first_direction === "Red" ? "text-danger" : ""}>{r.first_direction ?? "—"}</td>
                    <td className={sideTone(r.side)}>{r.side === "BOTH" ? "UNRESOLVED" : r.side ?? "—"}</td><td>{hm(r.breakout_time)}</td><td className="num-cell">{num(r.entry_price)}</td><td className="num-cell">{num(r.stop_loss)}</td>
                    <td>{hm(r.second_last_time)}</td><td className="num-cell">{num(r.second_last_close)}</td>
                    <td className={`num-cell ${tone(r.second_last_change_pct)}`}>{pct(r.second_last_change_pct)}</td>
                    <td>{hm(r.exit_time)}</td><td className="num-cell">{num(r.exit_price)}</td>
                    <td><span className="badge">{r.exit_reason}</span></td>
                    <td className={`num-cell ${tone(r.pnl_points)}`}>{num(r.pnl_points)}</td>
                    <td className={`num-cell ${tone(r.pnl_pct)}`}>{pct(r.pnl_pct)}</td>
                    <td className="muted small">{r.quality}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        !progress && (
          <div className="card state-block" style={{ marginTop: 16 }}>
            <div className="state-title">No {symbol} backtest yet</div>
            <div className="state-subtitle">Pick a date range and run the backtest on real 15-minute candles.</div>
          </div>
        )
      )}

      {manual && (() => {
        const rows = compareWithManual(manual.rows, result?.rows ?? []);
        const sum = summarizeComparison(rows);
        return (
          <div style={{ marginTop: 16 }}>
            <div className="history-detail-header">
              <h3 style={{ margin: 0 }}>Your Excel vs backtest — {manual.filename}</h3>
              <span style={{ display: "flex", gap: 8 }}>
                <button className="secondary-button" disabled={!result}
                  onClick={() => saveBlob(new Blob([compareToCsv(rows)], { type: "text/csv;charset=utf-8;" }), `excel-vs-backtest_${result?.symbol ?? symbol}_${result?.from ?? ""}_to_${result?.to ?? ""}.csv`)}>
                  Export comparison (CSV)
                </button>
                <button className="secondary-button" onClick={() => setManual(null)}>Remove</button>
              </span>
            </div>
            {!result && <p className="muted small">Run the backtest for the same dates to compare ({manual.rows.length} Excel rows loaded).</p>}
            {result && (
              <p className="muted small">
                {sum.compared} dates compared · {sum.noData} with no market data in this run · avg first-candle % difference{" "}
                {sum.avgCandleDiff == null ? "—" : `${num(sum.avgCandleDiff)} pts`} · days agreeing on side and profit/loss: {sum.callMatches}/{sum.callRows}
                {manual.skipped.length > 0 && ` · ${manual.skipped.length} unreadable Excel row(s) skipped`}
              </p>
            )}
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Date</th><th>Excel side</th><th>Backtest side</th><th className="num-cell">Excel candle %</th><th className="num-cell">Backtest candle %</th>
                    <th className="num-cell">Diff</th><th>Excel result</th><th>Backtest result</th>
                    <th className="num-cell">Excel EOD %</th><th className="num-cell">Backtest P&amp;L %</th><th>Verdict</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.date} style={r.verdict === "DIFFERENT" ? { background: "var(--warning-soft)" } : undefined}>
                      <td>{r.date}</td><td>{r.side ?? "—"}</td><td>{r.backtestSide ?? "—"}</td>
                      <td className="num-cell">{pct(r.excelCandlePct)}</td><td className="num-cell">{pct(r.backtestCandlePct)}</td>
                      <td className="num-cell">{r.candleDiff == null ? "—" : num(r.candleDiff)}</td>
                      <td>{r.excelOutcome ?? "—"}</td><td>{r.backtestOutcome ?? "no data"}</td>
                      <td className="num-cell">{pct(r.excelEodPct)}</td><td className="num-cell">{pct(r.backtestPnlPct)}</td>
                      <td>
                        <span className={r.verdict === "MATCH" ? "badge badge-good" : r.verdict === "DIFFERENT" ? "badge badge-highrisk" : "badge badge-neutral"}>
                          {r.verdict === "NO_DATA" ? "no data" : r.verdict}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        );
      })()}
    </div>
  );
}
