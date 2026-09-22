import { useEffect, useMemo, useState } from "react";
import { InstrumentBadge } from "../components/InstrumentBadge";
import { exportSnapshotToCsv } from "../services/historyExport";
import {
  getResultsForSnapshot,
  listSnapshots,
  type HistoryResultRow,
  type HistorySnapshotMeta,
} from "../services/localHistoryDb";

/**
 * Permanent, device-local Scan History. Reads ONLY the browser's own
 * IndexedDB (see services/localHistoryDb.ts) — never calls Angel One, never
 * recalculates a strategy, and is completely unaffected by a Render
 * restart/redeploy, since Render never held this data in the first place.
 */

function fmtDate(dateKey: string): string {
  const [y, m, d] = dateKey.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

function fmtDuration(seconds: number | null): string {
  if (seconds === null) return "—";
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s}s`;
}

function statusChipClass(status: HistorySnapshotMeta["status"]): string {
  if (status === "completed") return "chip chip-pass";
  if (status === "running") return "chip";
  return "chip chip-fail";
}

export function ScanHistoryPage() {
  const [snapshots, setSnapshots] = useState<HistorySnapshotMeta[] | null>(null);
  const [selected, setSelected] = useState<HistorySnapshotMeta | null>(null);
  const [rows, setRows] = useState<HistoryResultRow[] | null>(null);
  const [compareWith, setCompareWith] = useState<HistorySnapshotMeta | null>(null);
  const [compareRows, setCompareRows] = useState<HistoryResultRow[] | null>(null);

  const [symbolSearch, setSymbolSearch] = useState("");
  const [instrumentFilter, setInstrumentFilter] = useState<"all" | "FUTURE" | "EQUITY">("all");
  const [strategyFilter, setStrategyFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState<"all" | "PRD_FORMING" | "PRD_CONFIRMED">("all");
  const [timeframeFilter, setTimeframeFilter] = useState("all");

  function refresh() {
    listSnapshots().then(setSnapshots);
  }

  useEffect(refresh, []);

  useEffect(() => {
    if (!selected) {
      setRows(null);
      return;
    }
    getResultsForSnapshot(selected.localId).then(setRows);
  }, [selected]);

  useEffect(() => {
    if (!compareWith) {
      setCompareRows(null);
      return;
    }
    getResultsForSnapshot(compareWith.localId).then(setCompareRows);
  }, [compareWith]);

  const byDate = useMemo(() => {
    const map = new Map<string, HistorySnapshotMeta[]>();
    for (const s of snapshots ?? []) {
      const list = map.get(s.scanDate) ?? [];
      list.push(s);
      map.set(s.scanDate, list);
    }
    return Array.from(map.entries()).sort((a, b) => b[0].localeCompare(a[0]));
  }, [snapshots]);

  const strategyOptions = useMemo(() => {
    const set = new Set((rows ?? []).map((r) => r.strategy).filter(Boolean));
    return ["all", ...Array.from(set).sort()];
  }, [rows]);

  const filteredRows = useMemo(() => {
    let list = rows ?? [];
    if (symbolSearch.trim()) {
      const q = symbolSearch.trim().toUpperCase();
      list = list.filter((r) => r.symbol.toUpperCase().includes(q));
    }
    if (instrumentFilter !== "all") list = list.filter((r) => r.instrumentType === instrumentFilter);
    if (strategyFilter !== "all") list = list.filter((r) => r.strategy === strategyFilter);
    if (statusFilter !== "all") list = list.filter((r) => r.status === statusFilter);
    if (timeframeFilter !== "all") list = list.filter((r) => r.timeframe === timeframeFilter);
    return list;
  }, [rows, symbolSearch, instrumentFilter, strategyFilter, statusFilter, timeframeFilter]);

  const timeframeOptions = useMemo(() => {
    const set = new Set((rows ?? []).map((r) => r.timeframe).filter(Boolean) as string[]);
    return ["all", ...Array.from(set).sort()];
  }, [rows]);

  const comparison = useMemo(() => {
    if (!rows || !compareRows) return null;
    const key = (r: HistoryResultRow) => `${r.symbol}|${r.strategy}|${r.timeframe ?? ""}`;
    const current = new Map(rows.map((r) => [key(r), r]));
    const previous = new Map(compareRows.map((r) => [key(r), r]));
    const added = [...current.keys()].filter((k) => !previous.has(k)).map((k) => current.get(k)!);
    const removed = [...previous.keys()].filter((k) => !current.has(k)).map((k) => previous.get(k)!);
    const continuedKeys = [...current.keys()].filter((k) => previous.has(k));
    const changed = continuedKeys
      .map((k) => ({ before: previous.get(k)!, after: current.get(k)! }))
      .filter((pair) => pair.before.status !== pair.after.status);
    const unchanged = continuedKeys.length - changed.length;
    return { added, removed, changed, unchangedCount: unchanged };
  }, [rows, compareRows]);

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Scan History</h1>
          <p className="page-subtitle">
            Permanent, device-local history — stored in this browser (IndexedDB), never on the server. A Render
            restart or redeploy never affects it.
          </p>
        </div>
      </div>

      {snapshots === null && <div className="card state-block">Loading…</div>}

      {snapshots !== null && snapshots.length === 0 && (
        <div className="card state-block">
          <div className="state-title">No local history yet</div>
          <div className="state-subtitle">Run a scan from the Dashboard — every scan is saved here as it runs.</div>
        </div>
      )}

      {snapshots !== null && snapshots.length > 0 && (
        <div className="history-layout">
          <div className="history-date-list">
            {byDate.map(([date, scans]) => (
              <div key={date} className="card history-date-card">
                <h3 className="history-date-heading">{fmtDate(date)}</h3>
                {scans
                  .sort((a, b) => b.startedAt.localeCompare(a.startedAt))
                  .map((s) => (
                    <button
                      key={s.localId}
                      type="button"
                      className={selected?.localId === s.localId ? "history-scan-row active" : "history-scan-row"}
                      onClick={() => setSelected(s)}
                    >
                      <div className="history-scan-row-top">
                        <span className="history-scan-time">{s.scanTime.slice(0, 5)}</span>
                        <span className={statusChipClass(s.status)}>{s.status}</span>
                      </div>
                      <div className="muted small">
                        {s.scanType === "a_group" ? "A Group Scanner" : s.scanType} · {s.totalStocks} stocks ·{" "}
                        {s.signalCount} signals{s.failedStocks > 0 && <> · {s.failedStocks} failed</>}
                      </div>
                      {compareWith?.localId !== s.localId && selected?.localId !== s.localId && (
                        <span
                          className="history-compare-link"
                          onClick={(e) => {
                            e.stopPropagation();
                            setCompareWith(s);
                          }}
                        >
                          Compare against this
                        </span>
                      )}
                    </button>
                  ))}
              </div>
            ))}
          </div>

          <div className="history-detail">
            {!selected && (
              <div className="card state-block">
                <div className="state-title">Select a scan</div>
                <div className="state-subtitle">Pick a date and time on the left to see its saved results.</div>
              </div>
            )}

            {selected && (
              <>
                <div className="card">
                  <div className="history-detail-header">
                    <div>
                      <h2 style={{ margin: 0 }}>
                        {fmtDate(selected.scanDate)} — {selected.scanTime.slice(0, 5)}
                      </h2>
                      <p className="muted small" style={{ margin: "4px 0 0" }}>
                        {selected.totalStocks} stocks · {selected.successfulStocks} scanned OK ·{" "}
                        {selected.failedStocks} failed · {selected.signalCount} signals · duration{" "}
                        {fmtDuration(selected.durationSeconds)}
                      </p>
                    </div>
                    <div style={{ display: "flex", gap: 8 }}>
                      <span className={statusChipClass(selected.status)}>{selected.status}</span>
                      <button
                        className="secondary-button"
                        disabled={!rows}
                        onClick={() => rows && exportSnapshotToCsv(selected, rows)}
                      >
                        Export CSV
                      </button>
                    </div>
                  </div>
                </div>

                <div className="card filters-row filter-panel">
                  <label>
                    Search symbol
                    <input value={symbolSearch} onChange={(e) => setSymbolSearch(e.target.value)} placeholder="e.g. RELIANCE" />
                  </label>
                  <label>
                    Instrument
                    <select value={instrumentFilter} onChange={(e) => setInstrumentFilter(e.target.value as typeof instrumentFilter)}>
                      <option value="all">All</option>
                      <option value="FUTURE">Future</option>
                      <option value="EQUITY">Equity</option>
                    </select>
                  </label>
                  <label>
                    Strategy
                    <select value={strategyFilter} onChange={(e) => setStrategyFilter(e.target.value)}>
                      {strategyOptions.map((s) => (
                        <option key={s} value={s}>
                          {s === "all" ? "All" : s}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    PRD status
                    <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)}>
                      <option value="all">All</option>
                      <option value="PRD_FORMING">PRD Forming</option>
                      <option value="PRD_CONFIRMED">PRD Confirmed</option>
                    </select>
                  </label>
                  <label>
                    Timeframe
                    <select value={timeframeFilter} onChange={(e) => setTimeframeFilter(e.target.value)}>
                      {timeframeOptions.map((tf) => (
                        <option key={tf} value={tf}>
                          {tf === "all" ? "All" : tf}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                <div className="card table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Symbol</th>
                        <th>Strategy</th>
                        <th>Timeframe</th>
                        <th>Status</th>
                        <th className="num-cell">Price</th>
                        <th className="num-cell">RSI</th>
                        <th>A</th>
                        <th>B</th>
                        <th>Details</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredRows.length === 0 ? (
                        <tr>
                          <td colSpan={9} className="muted small" style={{ padding: 16 }}>
                            No rows match these filters.
                          </td>
                        </tr>
                      ) : (
                        filteredRows.map((r) => (
                          <tr key={r.id}>
                            <td className="symbol-cell">
                              {r.symbol}
                              <InstrumentBadge type={r.instrumentType} />
                            </td>
                            <td>{r.strategy || "—"}</td>
                            <td>{r.timeframe ?? "—"}</td>
                            <td>
                              <span className={r.status === "DATA_UNAVAILABLE" ? "chip chip-fail" : "chip"}>{r.status}</span>
                            </td>
                            <td className="num-cell">{r.price !== null ? `₹${r.price.toFixed(2)}` : "—"}</td>
                            <td className="num-cell">{r.rsi !== null ? r.rsi.toFixed(1) : "—"}</td>
                            <td className="muted small">
                              {r.aDate ? `${r.aDate} · ${r.aPrice ?? "—"} · RSI ${r.aRsi ?? "—"}` : "—"}
                            </td>
                            <td className="muted small">
                              {r.bDate ? `${r.bDate} · ${r.bPrice ?? "—"} · RSI ${r.bRsi ?? "—"}` : "—"}
                            </td>
                            <td className="explanation-cell muted small">{r.details || "—"}</td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </>
            )}

            {compareWith && comparison && (
              <div className="card">
                <div className="history-detail-header">
                  <h2 style={{ margin: 0 }}>
                    Comparison: {selected ? `${fmtDate(selected.scanDate)} ${selected.scanTime.slice(0, 5)}` : "—"} vs{" "}
                    {fmtDate(compareWith.scanDate)} {compareWith.scanTime.slice(0, 5)}
                  </h2>
                  <button className="secondary-button" onClick={() => setCompareWith(null)}>
                    Close comparison
                  </button>
                </div>
                <p className="muted small">Read entirely from local history — no Angel One calls.</p>
                <div className="chip-row" style={{ marginBottom: 10 }}>
                  <span className="chip chip-pass">{comparison.added.length} new</span>
                  <span className="chip chip-fail">{comparison.removed.length} removed</span>
                  <span className="chip">{comparison.changed.length} status changed</span>
                  <span className="muted small">{comparison.unchangedCount} unchanged</span>
                </div>
                {comparison.added.length > 0 && (
                  <div className="live-results">
                    {comparison.added.map((r, i) => (
                      <span key={i} className="live-result-chip">
                        + {r.symbol}
                        <InstrumentBadge type={r.instrumentType} /> · {r.strategy}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
