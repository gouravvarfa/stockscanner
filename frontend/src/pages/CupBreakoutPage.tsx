import { useEffect, useMemo, useState } from "react";
import { InstrumentBadge } from "../components/InstrumentBadge";
import { useChart } from "../chart/ChartContext";
import { useLocalHistoryWriter } from "../hooks/useLocalHistoryWriter";
import { useScanJob } from "../hooks/useScanJob";
import { fmtDuration } from "../services/scanJobsApi";

const SCAN_TYPE = "cup_breakout";

/**
 * Cup Breakout — a completely separate long-term MONTHLY pattern scanner.
 * NOT part of the existing strategy pipeline (System One/GFS/Advanced
 * GFS/PRD/NRD/Value Buy) — its own scan_type ("cup_breakout") going through
 * the SAME generic background-job machinery every other scan uses
 * (useScanJob, partial/progress polling, 24h cache), so this page reuses
 * that machinery without any Cup-specific change to it.
 */

interface CupResult {
  symbol: string;
  instrument_type: "FUTURE" | "EQUITY" | null;
  status: string;
  left_rim_date: string | null;
  left_rim_price: number | null;
  cup_low_date: string | null;
  cup_low_price: number | null;
  cup_depth_percent: number | null;
  cup_age_months: number | null;
  cup_age_years: number | null;
  recovery_percent: number | null;
  potential_breakout_level: number | null;
  latest_monthly_close: number | null;
  distance_to_breakout_percent: number | null;
  breakout_date: string | null;
  breakout_price: number | null;
  breakout_percent: number | null;
  breakout_volume: number | null;
  average_monthly_volume: number | null;
  volume_ratio: number | null;
  handle_status: string;
  history_years_available: number | null;
  updated_at: string;
  // Structure fields (present on results from 2026-09-25 onward; optional
  // so older cached/IndexedDB results without them still render).
  trend_before_cup?: string | null;
  trend_start_date?: string | null;
  trend_start_price?: number | null;
  cup_bottom_date?: string | null;
  cup_bottom_price?: number | null;
  right_rim_date?: string | null;
  right_rim_price?: number | null;
  breakout_level?: number | null;
  handle_start_date?: string | null;
  handle_end_date?: string | null;
  handle_low_price?: number | null;
  cup_type?: string | null;
}

interface CupScanResult {
  started_at: string;
  finished_at: string;
  execution_seconds: number;
  stocks_scanned: number;
  stocks_failed: number;
  failed_symbols: string[];
  results: CupResult[];
}

const STATUS_TABS = [
  { key: "all", label: "All" },
  { key: "EARLY_CUP", label: "Early Cup" },
  { key: "NEAR_BREAKOUT", label: "Near Breakout" },
  { key: "BREAKOUT_FORMING", label: "Breakout Forming" },
  { key: "BREAKOUT_CONFIRMED", label: "Breakout Confirmed" },
  { key: "RECENT_BREAKOUT", label: "Recent Breakout" },
] as const;

type StatusTabKey = (typeof STATUS_TABS)[number]["key"];
type SortKey = "closest_breakout" | "deepest_cup" | "highest_recovery" | "longest_cup" | "recent_breakout" | "setup_quality";

function fmtPrice(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : `₹${v.toFixed(2)}`;
}
function fmtPct(v: number | null | undefined, signed = false): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const sign = signed && v > 0 ? "+" : "";
  return `${sign}${v.toFixed(1)}%`;
}
function fmtDay(v: string | null | undefined): string {
  return v ? String(v).slice(0, 10) : "—";
}
function statusLabel(status: string): string {
  return status.replace(/_/g, " ");
}
function statusChipClass(status: string): string {
  if (status === "BREAKOUT_CONFIRMED" || status === "RECENT_BREAKOUT") return "chip chip-pass";
  if (status === "NEAR_BREAKOUT" || status === "BREAKOUT_FORMING") return "chip chip-warn";
  return "chip";
}

// A rough, purely descriptive "setup quality" score for the "Setup Quality"
// sort — closer to breakout + deeper (within the valid band) + a developed
// right side all count in its favor. Never used to filter/reject a result,
// only to order them — see backend/strategies/cup.py's own explicit
// "deeper is not automatically better" note.
function setupQualityScore(r: CupResult): number {
  const distance = r.distance_to_breakout_percent ?? 100;
  const depth = r.cup_depth_percent ?? 0;
  const recovery = r.recovery_percent ?? 0;
  const statusBonus =
    r.status === "BREAKOUT_CONFIRMED" ? 40 : r.status === "RECENT_BREAKOUT" ? 30 : r.status === "NEAR_BREAKOUT" ? 20 : r.status === "BREAKOUT_FORMING" ? 25 : 0;
  return statusBonus + Math.max(0, 20 - Math.abs(distance)) + Math.min(recovery, 100) / 5 + Math.min(depth, 50) / 5;
}

function partialToCupResult(signal: { extra: Record<string, unknown> }): CupResult | null {
  const e = signal.extra;
  if (!e || typeof e.status !== "string") return null;
  return e as unknown as CupResult;
}

export function CupBreakoutPage() {
  const { result, partial, progressLog, job, running, error, run, runFresh, cancel } = useScanJob<CupScanResult>(SCAN_TYPE);
  const { openChart } = useChart();

  // Permanent, device-local Scan History (IndexedDB) — same mechanism the
  // A Group scan already uses (frontend/src/hooks/useLocalHistoryWriter.ts),
  // so a Render restart never loses a completed Cup Breakout scan either.
  useLocalHistoryWriter(SCAN_TYPE, job, partial, progressLog, result);

  const [activeTab, setActiveTab] = useState<StatusTabKey>("all");
  const [symbolSearch, setSymbolSearch] = useState("");
  const [distanceFilter, setDistanceFilter] = useState<"all" | "0-2" | "2-5" | "5-10">("all");
  const [depthFilter, setDepthFilter] = useState<"all" | "10-20" | "20-30" | "30-40" | "40+">("all");
  const [sortKey, setSortKey] = useState<SortKey>("closest_breakout");

  useEffect(() => setActiveTab("all"), []);

  // Prefer the finished/cached result; while a scan is actively running (no
  // final `result` yet), fall back to the live `partial` stream so results
  // appear progressively, exactly like the Dashboard's PRD/NRD tabs do.
  const allResults: CupResult[] = useMemo(() => {
    if (result?.results) return result.results;
    const seen = new Map<string, CupResult>();
    for (const p of partial) {
      for (const s of p.signals) {
        const cup = partialToCupResult(s);
        if (cup) seen.set(p.symbol, { ...cup, symbol: p.symbol, instrument_type: p.instrument_type });
      }
    }
    return Array.from(seen.values());
  }, [result, partial]);

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: allResults.length };
    for (const r of allResults) c[r.status] = (c[r.status] ?? 0) + 1;
    return c;
  }, [allResults]);

  const filtered = useMemo(() => {
    let rows = allResults;
    if (activeTab !== "all") rows = rows.filter((r) => r.status === activeTab);
    if (symbolSearch.trim()) {
      const q = symbolSearch.trim().toUpperCase();
      rows = rows.filter((r) => r.symbol.toUpperCase().includes(q));
    }
    if (distanceFilter !== "all") {
      const [lo, hi] = distanceFilter.split("-").map(Number);
      rows = rows.filter((r) => r.distance_to_breakout_percent !== null && r.distance_to_breakout_percent >= lo && r.distance_to_breakout_percent <= hi);
    }
    if (depthFilter !== "all") {
      rows = rows.filter((r) => {
        const d = r.cup_depth_percent;
        if (d === null) return false;
        if (depthFilter === "10-20") return d >= 10 && d < 20;
        if (depthFilter === "20-30") return d >= 20 && d < 30;
        if (depthFilter === "30-40") return d >= 30 && d < 40;
        return d >= 40;
      });
    }
    const sorted = [...rows];
    sorted.sort((a, b) => {
      switch (sortKey) {
        case "deepest_cup":
          return (b.cup_depth_percent ?? -1) - (a.cup_depth_percent ?? -1);
        case "highest_recovery":
          return (b.recovery_percent ?? -1) - (a.recovery_percent ?? -1);
        case "longest_cup":
          return (b.cup_age_months ?? -1) - (a.cup_age_months ?? -1);
        case "recent_breakout":
          return (b.breakout_date ?? "").localeCompare(a.breakout_date ?? "");
        case "setup_quality":
          return setupQualityScore(b) - setupQualityScore(a);
        case "closest_breakout":
        default:
          return Math.abs(a.distance_to_breakout_percent ?? 999) - Math.abs(b.distance_to_breakout_percent ?? 999);
      }
    });
    return sorted;
  }, [allResults, activeTab, symbolSearch, distanceFilter, depthFilter, sortKey]);

  const qualifying = useMemo(() => allResults.filter((r) => r.status !== "EARLY_CUP"), [allResults]);
  const closestToBreakout = useMemo(
    () => [...allResults].filter((r) => r.distance_to_breakout_percent !== null).sort((a, b) => Math.abs(a.distance_to_breakout_percent!) - Math.abs(b.distance_to_breakout_percent!))[0] ?? null,
    [allResults],
  );
  const deepestCup = useMemo(
    () => [...allResults].filter((r) => r.cup_depth_percent !== null).sort((a, b) => b.cup_depth_percent! - a.cup_depth_percent!)[0] ?? null,
    [allResults],
  );
  const highestRecovery = useMemo(
    () => [...allResults].filter((r) => r.recovery_percent !== null).sort((a, b) => b.recovery_percent! - a.recovery_percent!)[0] ?? null,
    [allResults],
  );
  const mostRecentBreakout = useMemo(
    () => [...allResults].filter((r) => r.breakout_date).sort((a, b) => b.breakout_date!.localeCompare(a.breakout_date!))[0] ?? null,
    [allResults],
  );

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Cup Breakout Scanner</h1>
          <p className="page-subtitle">Long-term monthly Cup structures approaching or breaking resistance</p>
        </div>
        <div>
          {!running ? (
            <>
              <button className="primary-button" onClick={run}>Scan</button>
              <button className="secondary-button" onClick={runFresh} style={{ marginLeft: 8 }}>Fresh Scan</button>
            </>
          ) : (
            <button className="secondary-button stop-scan-button" onClick={cancel}>Stop Scan</button>
          )}
        </div>
      </div>

      {running && job && (
        <div className="card">
          <div className="history-detail-header">
            <div>
              Scanning: {job.current_symbol ?? "…"}
            </div>
            <div className="muted small">{job.processed} / {job.total || "?"} ({job.percentage.toFixed(1)}%)</div>
          </div>
          <div className="active-scan-bar" style={{ marginTop: 8 }}>
            <div className="active-scan-bar-fill" style={{ width: `${Math.min(job.percentage, 100)}%` }} />
          </div>
          <p className="muted small" style={{ marginTop: 6 }}>
            Elapsed {fmtDuration(job.elapsed_seconds)} · ETA {job.eta_seconds === null ? "Estimating…" : fmtDuration(job.eta_seconds)} ·{" "}
            {qualifying.length} candidates found so far
          </p>
        </div>
      )}

      {error && !running && <div className="card state-block"><div className="state-title">{error}</div></div>}

      {allResults.length > 0 && (
        <>
          <div className="grid-4" style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 16 }}>
            <TopCard title="Closest to Breakout" result={closestToBreakout} metric={(r) => fmtPct(r.distance_to_breakout_percent)} />
            <TopCard title="Deepest Cup" result={deepestCup} metric={(r) => fmtPct(r.cup_depth_percent)} />
            <TopCard title="Highest Recovery" result={highestRecovery} metric={(r) => fmtPct(r.recovery_percent)} />
            <TopCard title="Recent Breakout" result={mostRecentBreakout} metric={(r) => fmtDay(r.breakout_date)} />
          </div>

          <div className="tabs">
            {STATUS_TABS.map((t) => (
              <button key={t.key} className={activeTab === t.key ? "tab active" : "tab"} onClick={() => setActiveTab(t.key)}>
                {t.label}
                <span className="tab-count">{counts[t.key] ?? 0}</span>
              </button>
            ))}
          </div>

          <div className="card filters-row filter-panel">
            <label>
              Search symbol
              <input value={symbolSearch} onChange={(e) => setSymbolSearch(e.target.value)} placeholder="e.g. BHEL" />
            </label>
            <label>
              Distance to breakout
              <select value={distanceFilter} onChange={(e) => setDistanceFilter(e.target.value as typeof distanceFilter)}>
                <option value="all">All</option>
                <option value="0-2">0–2%</option>
                <option value="2-5">2–5%</option>
                <option value="5-10">5–10%</option>
              </select>
            </label>
            <label>
              Cup depth
              <select value={depthFilter} onChange={(e) => setDepthFilter(e.target.value as typeof depthFilter)}>
                <option value="all">All</option>
                <option value="10-20">10–20%</option>
                <option value="20-30">20–30%</option>
                <option value="30-40">30–40%</option>
                <option value="40+">40%+</option>
              </select>
            </label>
            <label>
              Sort by
              <select value={sortKey} onChange={(e) => setSortKey(e.target.value as SortKey)}>
                <option value="closest_breakout">Closest to Breakout</option>
                <option value="deepest_cup">Deepest Cup</option>
                <option value="highest_recovery">Highest Recovery</option>
                <option value="longest_cup">Longest Cup</option>
                <option value="recent_breakout">Recent Breakout</option>
                <option value="setup_quality">Setup Quality</option>
              </select>
            </label>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th className="num-cell">Price</th>
                  <th className="num-cell">Breakout Level</th>
                  <th className="num-cell">Distance</th>
                  <th className="num-cell">Cup Depth</th>
                  <th className="num-cell">Recovery</th>
                  <th className="num-cell">Cup Age</th>
                  <th className="num-cell">Breakout %</th>
                  <th>Chart</th>
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 ? (
                  <tr><td colSpan={11} className="muted small" style={{ padding: 16 }}>No stocks match these filters.</td></tr>
                ) : (
                  filtered.map((r) => (
                    <tr key={r.symbol}>
                      <td className="symbol-cell">
                        <b>{r.symbol}</b>
                        <InstrumentBadge type={r.instrument_type} />
                      </td>
                      <td>{r.instrument_type ?? "—"}</td>
                      <td><span className={statusChipClass(r.status)}>{statusLabel(r.status)}</span></td>
                      <td className="num-cell">{fmtPrice(r.latest_monthly_close)}</td>
                      <td className="num-cell">{fmtPrice(r.potential_breakout_level)}</td>
                      <td className="num-cell">{fmtPct(r.distance_to_breakout_percent)}</td>
                      <td className="num-cell">{fmtPct(r.cup_depth_percent)}</td>
                      <td className="num-cell">{fmtPct(r.recovery_percent)}</td>
                      <td className="num-cell">{r.cup_age_years !== null ? `${r.cup_age_years.toFixed(1)}Y` : "—"}</td>
                      <td className="num-cell">{r.breakout_percent !== null ? fmtPct(r.breakout_percent, true) : "—"}</td>
                      <td>
                        <button
                          type="button"
                          className="secondary-button"
                          onClick={() =>
                            openChart(r.symbol, {
                              strategy: "CUP",
                              daily_rsi: null,
                              weekly_rsi: null,
                              monthly_rsi: null,
                              signal_date: r.updated_at,
                              divergence_timeframe: "MONTHLY",
                              explanation:
                                `Cup Breakout: ${statusLabel(r.status)} — left rim ${fmtPrice(r.left_rim_price)} on ${fmtDay(r.left_rim_date)}, ` +
                                `cup low ${fmtPrice(r.cup_low_price)} on ${fmtDay(r.cup_low_date)}, breakout level ${fmtPrice(r.potential_breakout_level)}.`,
                              cupStructure: {
                                trend_start_date: r.trend_start_date ?? null,
                                trend_start_price: r.trend_start_price ?? null,
                                left_rim_date: r.left_rim_date,
                                left_rim_price: r.left_rim_price,
                                cup_bottom_date: r.cup_bottom_date ?? r.cup_low_date,
                                cup_bottom_price: r.cup_bottom_price ?? r.cup_low_price,
                                right_rim_date: r.right_rim_date ?? null,
                                right_rim_price: r.right_rim_price ?? null,
                                breakout_level: r.breakout_level ?? r.potential_breakout_level,
                                breakout_date: r.breakout_date,
                                handle_start_date: r.handle_start_date ?? null,
                                handle_end_date: r.handle_end_date ?? null,
                                handle_low_price: r.handle_low_price ?? null,
                              },
                            })
                          }
                        >
                          Chart
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      {!running && allResults.length === 0 && !error && (
        <div className="card state-block">
          <div className="state-title">No Cup Breakout scan yet</div>
          <div className="state-subtitle">Run a scan to find long-term monthly Cup structures approaching or breaking resistance.</div>
        </div>
      )}
    </div>
  );
}

function TopCard({ title, result, metric }: { title: string; result: CupResult | null; metric: (r: CupResult) => string }) {
  return (
    <div className="card">
      <div className="muted small" style={{ marginBottom: 6 }}>{title}</div>
      {result ? (
        <>
          <div style={{ fontWeight: 700, fontSize: "1.1rem" }}>{result.symbol}</div>
          <div className="muted small">{metric(result)}</div>
        </>
      ) : (
        <div className="muted small">—</div>
      )}
    </div>
  );
}
