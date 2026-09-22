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

const ROWS_PREVIEW = 8;

function fmtDate(dateKey: string): string {
  const [y, m, d] = dateKey.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

function fmtTime(scanTime: string): string {
  const [h, m] = scanTime.split(":").map(Number);
  const period = h >= 12 ? "PM" : "AM";
  const h12 = h % 12 === 0 ? 12 : h % 12;
  return `${h12}:${String(m).padStart(2, "0")} ${period}`;
}

function fmtDuration(seconds: number | null): string {
  if (seconds === null) return "—";
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s}s`;
}

function fmtUpdated(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: true });
}

function statusChipClass(status: HistorySnapshotMeta["status"]): string {
  if (status === "completed") return "chip chip-pass";
  if (status === "running") return "chip";
  return "chip chip-fail";
}

function scanTypeLabel(scanType: string): string {
  if (scanType === "a_group") return "A Group Scanner";
  return scanType;
}

function resultStatusChipClass(status: string): string {
  if (status === "DATA_UNAVAILABLE" || status === "FAILED") return "chip chip-fail";
  if (status === "PRD_FORMING") return "chip chip-warn";
  if (status === "PRD_CONFIRMED" || status === "QUALIFIED") return "chip chip-pass";
  return "chip";
}

function strategyBadgeClass(strategy: string): string {
  const key = strategy.toLowerCase().replace(/\s+/g, "-");
  return `strategy-badge strategy-badge-${key}`;
}

export function ScanHistoryPage() {
  const [snapshots, setSnapshots] = useState<HistorySnapshotMeta[] | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [rowsByLocalId, setRowsByLocalId] = useState<Record<string, HistoryResultRow[]>>({});
  const [showAllRows, setShowAllRows] = useState<Record<string, boolean>>({});
  const [compareWith, setCompareWith] = useState<HistorySnapshotMeta | null>(null);
  const [compareRows, setCompareRows] = useState<HistoryResultRow[] | null>(null);

  const [symbolSearch, setSymbolSearch] = useState("");
  const [strategyFilter, setStrategyFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState<"all" | HistorySnapshotMeta["status"]>("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const [dateFilter, setDateFilter] = useState("");

  useEffect(() => {
    listSnapshots().then((list) => {
      setSnapshots(list);
      if (list.length > 0) setExpandedId(list[0].localId);
    });
  }, []);

  const expanded = useMemo(
    () => snapshots?.find((s) => s.localId === expandedId) ?? null,
    [snapshots, expandedId],
  );

  useEffect(() => {
    if (!expanded || rowsByLocalId[expanded.localId]) return;
    getResultsForSnapshot(expanded.localId).then((r) =>
      setRowsByLocalId((prev) => ({ ...prev, [expanded.localId]: r })),
    );
  }, [expanded, rowsByLocalId]);

  useEffect(() => {
    if (!compareWith) {
      setCompareRows(null);
      return;
    }
    getResultsForSnapshot(compareWith.localId).then(setCompareRows);
  }, [compareWith]);

  const typeOptions = useMemo(() => {
    const set = new Set((snapshots ?? []).map((s) => s.scanType));
    return ["all", ...Array.from(set).sort()];
  }, [snapshots]);

  const filteredSnapshots = useMemo(() => {
    let list = snapshots ?? [];
    if (typeFilter !== "all") list = list.filter((s) => s.scanType === typeFilter);
    if (statusFilter !== "all") list = list.filter((s) => s.status === statusFilter);
    if (dateFilter) list = list.filter((s) => s.scanDate === dateFilter);
    return list;
  }, [snapshots, typeFilter, statusFilter, dateFilter]);

  const rows = expanded ? rowsByLocalId[expanded.localId] ?? null : null;

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
    if (strategyFilter !== "all") list = list.filter((r) => r.strategy === strategyFilter);
    return list;
  }, [rows, symbolSearch, strategyFilter]);

  const visibleRows =
    expanded && showAllRows[expanded.localId] ? filteredRows : filteredRows.slice(0, ROWS_PREVIEW);

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

  function toggle(s: HistorySnapshotMeta) {
    setExpandedId((cur) => (cur === s.localId ? null : s.localId));
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Scan History</h1>
          <p className="page-subtitle">View and manage your past scans, results and performance</p>
        </div>
      </div>

      {snapshots !== null && snapshots.length > 0 && (
        <div className="card history-toolbar">
          <div className="history-toolbar-filters">
            <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
              {typeOptions.map((t) => (
                <option key={t} value={t}>
                  {t === "all" ? "All Types" : scanTypeLabel(t)}
                </option>
              ))}
            </select>
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)}>
              <option value="all">All Status</option>
              <option value="completed">Completed</option>
              <option value="running">Running</option>
              <option value="stopped">Stopped</option>
              <option value="failed">Failed</option>
            </select>
            <select value={strategyFilter} onChange={(e) => setStrategyFilter(e.target.value)}>
              {strategyOptions.map((s) => (
                <option key={s} value={s}>
                  {s === "all" ? "All Strategies" : s}
                </option>
              ))}
            </select>
            <input
              type="date"
              value={dateFilter}
              onChange={(e) => setDateFilter(e.target.value)}
              aria-label="Select date"
            />
            {dateFilter && (
              <button type="button" className="secondary-button" onClick={() => setDateFilter("")}>
                Clear date
              </button>
            )}
          </div>
          <input
            className="history-toolbar-search"
            value={symbolSearch}
            onChange={(e) => setSymbolSearch(e.target.value)}
            placeholder="Search symbol…"
          />
        </div>
      )}

      {snapshots === null && <div className="card state-block">Loading…</div>}

      {snapshots !== null && snapshots.length === 0 && (
        <div className="card state-block">
          <div className="state-title">No local history yet</div>
          <div className="state-subtitle">Run a scan from the Dashboard — every scan is saved here as it runs.</div>
        </div>
      )}

      {snapshots !== null && snapshots.length > 0 && filteredSnapshots.length === 0 && (
        <div className="card state-block">
          <div className="state-title">No scans match these filters</div>
        </div>
      )}

      <div className="history-accordion">
        {filteredSnapshots.map((s) => {
          const isOpen = expandedId === s.localId;
          const localRows = rowsByLocalId[s.localId];
          return (
            <div key={s.localId} className={isOpen ? "card history-scan-card open" : "card history-scan-card"}>
              <button type="button" className="history-scan-header" onClick={() => toggle(s)}>
                <span className={`history-chevron ${isOpen ? "open" : ""}`}>▸</span>
                <span className="history-scan-datetime">
                  <span className="history-scan-date">{fmtDate(s.scanDate)}</span>
                  <span className="history-scan-time">{fmtTime(s.scanTime)}</span>
                </span>
                <span className="strategy-badge strategy-badge-agroup">{scanTypeLabel(s.scanType)}</span>
                <span className="history-scan-stats">
                  <span className="history-stat">
                    <span className="history-stat-dot" /> {s.totalStocks} scanned
                  </span>
                  <span className="history-stat history-stat-pass">
                    <span className="history-stat-dot" /> {s.signalCount} signals
                  </span>
                  {s.failedStocks > 0 && (
                    <span className="history-stat history-stat-fail">
                      <span className="history-stat-dot" /> {s.failedStocks} failed
                    </span>
                  )}
                  <span className="history-stat">{fmtDuration(s.durationSeconds)}</span>
                </span>
                <span className={statusChipClass(s.status)}>{s.status}</span>
              </button>

              {isOpen && (
                <div className="history-scan-body">
                  <div className="history-scan-body-header">
                    <h3 style={{ margin: 0 }}>Scan Results ({filteredRows.length} signals)</h3>
                    <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                      {filteredRows.length > ROWS_PREVIEW && (
                        <button
                          type="button"
                          className="history-view-all-link"
                          onClick={() =>
                            setShowAllRows((prev) => ({ ...prev, [s.localId]: !prev[s.localId] }))
                          }
                        >
                          {showAllRows[s.localId] ? "Show less" : `View All (${filteredRows.length})`}
                        </button>
                      )}
                      <button
                        className="secondary-button"
                        disabled={!localRows}
                        onClick={() => localRows && exportSnapshotToCsv(s, localRows)}
                      >
                        Export CSV
                      </button>
                      {compareWith?.localId !== s.localId && (
                        <button type="button" className="secondary-button" onClick={() => setCompareWith(s)}>
                          Compare
                        </button>
                      )}
                    </div>
                  </div>

                  {!rows && <div className="muted small" style={{ padding: 16 }}>Loading results…</div>}

                  {rows && (
                    <>
                      <div className="table-wrap history-table-wrap">
                        <table>
                          <thead>
                            <tr>
                              <th>#</th>
                              <th>Symbol</th>
                              <th>Type</th>
                              <th>Strategy</th>
                              <th>Timeframe</th>
                              <th>Status</th>
                              <th className="num-cell">Price</th>
                              <th className="num-cell">RSI</th>
                              <th>A / B</th>
                              <th>Distance</th>
                              <th>Updated</th>
                            </tr>
                          </thead>
                          <tbody>
                            {visibleRows.length === 0 ? (
                              <tr>
                                <td colSpan={11} className="muted small" style={{ padding: 16 }}>
                                  No rows match these filters.
                                </td>
                              </tr>
                            ) : (
                              visibleRows.map((r, i) => (
                                <tr key={r.id} className="history-result-row">
                                  <td className="muted small">{i + 1}</td>
                                  <td className="symbol-cell" data-label="Symbol">
                                    <b>{r.symbol}</b>
                                  </td>
                                  <td data-label="Type">
                                    <InstrumentBadge type={r.instrumentType} />
                                  </td>
                                  <td data-label="Strategy">
                                    <span className={strategyBadgeClass(r.strategy || "—")}>{r.strategy || "—"}</span>
                                  </td>
                                  <td data-label="Timeframe">{r.timeframe ?? "—"}</td>
                                  <td data-label="Status">
                                    <span className={resultStatusChipClass(r.status)}>{r.status}</span>
                                  </td>
                                  <td className="num-cell" data-label="Price">
                                    {r.price !== null ? `₹${r.price.toFixed(2)}` : "—"}
                                  </td>
                                  <td className="num-cell" data-label="RSI">
                                    {r.rsi !== null ? r.rsi.toFixed(1) : "—"}
                                  </td>
                                  <td className="muted small" data-label="A / B">
                                    {r.aDate ? `${r.aDate.slice(5)} / ${r.bDate?.slice(5) ?? "—"}` : "—"}
                                  </td>
                                  <td className="muted small" data-label="Distance">
                                    {r.abDistance !== null ? `${r.abDistance} bars` : "—"}
                                  </td>
                                  <td className="muted small" data-label="Updated">
                                    {fmtUpdated(r.updatedAt)}
                                  </td>
                                </tr>
                              ))
                            )}
                          </tbody>
                        </table>
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {compareWith && comparison && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="history-detail-header">
            <h2 style={{ margin: 0 }}>
              Comparison: {expanded ? `${fmtDate(expanded.scanDate)} ${fmtTime(expanded.scanTime)}` : "—"} vs{" "}
              {fmtDate(compareWith.scanDate)} {fmtTime(compareWith.scanTime)}
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
  );
}
