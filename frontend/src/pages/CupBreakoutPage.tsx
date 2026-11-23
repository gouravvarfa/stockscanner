import { useEffect, useMemo, useState } from "react";
import { InstrumentBadge } from "../components/InstrumentBadge";
import { CupMotif, PageHero } from "../components/PageHero";
import { StockLogo } from "../components/StockLogo";
import { useChart } from "../chart/ChartContext";
import { useLocalHistoryWriter } from "../hooks/useLocalHistoryWriter";
import { useScanJob } from "../hooks/useScanJob";
import { newerOf, useEodResult } from "../hooks/useEodResult";
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
  /** strong sectors this stock belongs to (NSE end-of-day result, 2026-11-23) */
  sectors?: { key: string; label: string; status: string }[];
  company_name?: string | null;
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
  // Cup Level 1 trade levels (2026-10-31) — all computed server-side in
  // backend/strategies/cup_levels.py; the page only displays them.
  neckline?: number | null;
  cup_start_date?: string | null;
  current_price?: number | null;
  status_group?: "CUP_FORMING" | "AWAITING_BREAKOUT" | "BREAKOUT_CONFIRMED" | null;
  entry_price?: number | null;
  stop_loss?: number | null;
  target_1?: number | null;
  target_2?: number | null;
  target_3?: number | null;
  targets_crossed?: number | null;
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

const GROUP_LABELS: Record<string, string> = {
  CUP_FORMING: "Cup Forming",
  AWAITING_BREAKOUT: "Awaiting Breakout",
  BREAKOUT_CONFIRMED: "Breakout Confirmed",
};

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
  const { result, partial, progressLog, job, running, error, run, runFresh, cancel, cache, clearSaved, queued } = useScanJob<CupScanResult>(SCAN_TYPE);
  const { openChart } = useChart();
  const eod = useEodResult<CupScanResult>("cup");
  const { shown, isEod } = newerOf(result, eod);

  // Permanent, device-local Scan History (IndexedDB) — same mechanism the
  // A Group scan already uses (frontend/src/hooks/useLocalHistoryWriter.ts),
  // so a Render restart never loses a completed Cup Breakout scan either.
  useLocalHistoryWriter(SCAN_TYPE, job, partial, progressLog, result);

  const [activeTab, setActiveTab] = useState<StatusTabKey>("all");
  const [symbolSearch, setSymbolSearch] = useState("");
  const [strongOnly, setStrongOnly] = useState(false);
  const openCupChart = (r: CupResult) =>
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
                            });

  const [distanceFilter, setDistanceFilter] = useState<"all" | "0-2" | "2-5" | "5-10">("all");
  const [depthFilter, setDepthFilter] = useState<"all" | "10-20" | "20-30" | "30-40" | "40+">("all");
  const [sortKey, setSortKey] = useState<SortKey>("closest_breakout");

  useEffect(() => setActiveTab("all"), []);

  // Prefer the finished/cached result; while a scan is actively running (no
  // final `result` yet), fall back to the live `partial` stream so results
  // appear progressively, exactly like the Dashboard's PRD/NRD tabs do.
  const allResults: CupResult[] = useMemo(() => {
    if (!running && shown?.results) return shown.results;
    if (result?.results) return result.results;
    const seen = new Map<string, CupResult>();
    for (const p of partial) {
      for (const s of p.signals) {
        const cup = partialToCupResult(s);
        if (cup) seen.set(p.symbol, { ...cup, symbol: p.symbol, instrument_type: p.instrument_type });
      }
    }
    return Array.from(seen.values());
  }, [result, partial, shown, running]);

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: allResults.length };
    for (const r of allResults) c[r.status] = (c[r.status] ?? 0) + 1;
    return c;
  }, [allResults]);

  const filtered = useMemo(() => {
    let rows = allResults;
    if (activeTab !== "all") rows = rows.filter((r) => r.status === activeTab);
    if (strongOnly) rows = rows.filter((r) => (r.sectors ?? []).length > 0);
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
  }, [allResults, activeTab, symbolSearch, distanceFilter, depthFilter, sortKey, strongOnly]);

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
      <PageHero
        tone="cup"
        eyebrow="Scanner · monthly candles"
        title="Cup Breakout"
        subtitle="Long-term cups on the monthly chart, across all NSE stocks — the ones nearing their rim and the ones breaking out of it."
        motif={<CupMotif />}
      >
        <div className="hero-actions">
          {!running && eod ? (
            <>
              <span className="eod-ready">✓ Ready · NSE data of {new Date(`${eod.data_as_of}T00:00:00`).toLocaleDateString("en-IN", { day: "2-digit", month: "short" })} · no scan needed</span>
            </>
          ) : !running ? (
            <>
              <button className="primary-button" onClick={run}>Scan</button>
              <button className="secondary-button" onClick={runFresh} style={{ marginLeft: 8 }}>Fresh Scan</button>
            </>
          ) : (
            <button className="secondary-button stop-scan-button" onClick={cancel}>Stop Scan</button>
          )}
        </div>
      </PageHero>

      {isEod && !running && shown && (
        <div className="notice-banner eod-banner">
          <span>
            NSE end-of-day data as of <b>{new Date(`${(shown as CupScanResult & { data_as_of: string }).data_as_of}T00:00:00`).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" })}</b>
            {" "}· every NSE stock, up to 20 years of monthly candles · updated each evening, no scan needed
          </span>
        </div>
      )}
            {queued && (
        <div className="notice-banner queue-banner">
          <span>{queued}</span>
          <button type="button" className="secondary-button" onClick={() => void cancel()}>Cancel</button>
        </div>
      )}

      {/* The result lives only on this laptop (browser storage on its disk); Render keeps no copy (2026-11-22). */}
      {!running && result && (
        <div className="cup-saved">
          <span>
            Saved on this device{cache?.completed_at ? ` · scan of ${new Date(cache.completed_at).toLocaleString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" })}` : ""} · not stored on the server
          </span>
          <button
            type="button"
            className="secondary-button cup-delete"
            onClick={() => {
              if (window.confirm("Delete the saved Cup scan from this device?")) void clearSaved();
            }}
          >
            Delete
          </button>
        </div>
      )}

      {running && job && (
        <div className="card">
          <div className="history-detail-header">
            <div>
              Scanning: {job.current_symbol ?? "…"}
            </div>
            <div className="muted small">{job.processed} / {job.total || "?"} ({job.percentage.toFixed(1)}%)</div>
          </div>
          <div className="active-scan-bar" style={{ marginTop: 8 }}>
            <div className="active-scan-bar-fill" style={{ transform: `scaleX(${Math.min(job.percentage, 100) / 100})` }} />
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

          {allResults.some((r) => (r.sectors ?? []).length > 0) && (
            <section className="card cup-strong">
              <div className="dash-card-head">
                <div>
                  <h2>Strong sector cups</h2>
                  <p className="muted small">Cups in your sectors that are strong today (sector index daily, weekly and monthly RSI above 60). Tap a card for its chart.</p>
                </div>
                <span className="cup-strong-count">{allResults.filter((r) => (r.sectors ?? []).length > 0).length}</span>
              </div>
              <div className="cup-strong-grid">
                {allResults.filter((r) => (r.sectors ?? []).length > 0)
                  .sort((a, b) => Math.abs(a.distance_to_breakout_percent ?? 99) - Math.abs(b.distance_to_breakout_percent ?? 99))
                  .map((r) => (
                    <button key={r.symbol} type="button" className="cup-strong-card" onClick={() => openCupChart(r)}>
                      <span className="vb-best-top">
                        <span className="wk-logo"><StockLogo symbol={r.symbol} /></span>
                        <span className="vb-best-name"><b>{r.symbol}</b><small>{r.company_name ?? ""}</small></span>
                      </span>
                      <span className={statusChipClass(r.status)}>{statusLabel(r.status)}</span>
                      <span className="vb-best-meta">
                        <span>Breakout level <b>{fmtPrice(r.potential_breakout_level)}</b>{r.distance_to_breakout_percent != null ? ` · ${r.distance_to_breakout_percent.toFixed(1)}% away` : ""}</span>
                      </span>
                      <span className="cup-strong-secs">{(r.sectors ?? []).map((sc) => <span key={sc.key} className="vb-sec vb-sec-strong">{sc.label}</span>)}</span>
                    </button>
                  ))}
              </div>
            </section>
          )}

          <div className="cup-strong-bar">
            <div className="vb-seg" role="tablist" aria-label="Sectors">
              <button type="button" role="tab" aria-selected={!strongOnly} className={!strongOnly ? "active" : ""} onClick={() => setStrongOnly(false)}>
                All cups <b>{allResults.length}</b>
              </button>
              <button type="button" role="tab" aria-selected={strongOnly} className={strongOnly ? "active cup-strong-tab" : "cup-strong-tab"} onClick={() => setStrongOnly(true)}>
                Strong sector <b>{allResults.filter((r) => (r.sectors ?? []).length > 0).length}</b>
              </button>
            </div>
            <span className="muted small">Strong sector = your Weekly Sectors whose index daily, weekly and monthly RSI are all above 60 today</span>
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
                  <th>Company</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Group</th>
                  <th className="num-cell">Price</th>
                  <th className="num-cell">Neckline</th>
                  <th className="num-cell">Distance</th>
                  <th className="num-cell">Entry (+4%)</th>
                  <th className="num-cell">Stop Loss (−2%)</th>
                  <th className="num-cell">Target 1 (+10%)</th>
                  <th className="num-cell">Target 2 (+20%)</th>
                  <th className="num-cell">Target 3 (+30%)</th>
                  <th>Cup Start</th>
                  <th className="num-cell">Cup Duration</th>
                  <th className="num-cell">Cup Depth</th>
                  <th className="num-cell">Recovery</th>
                  <th className="num-cell">Breakout %</th>
                  <th>Chart</th>
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 ? (
                  <tr><td colSpan={18} className="muted small" style={{ padding: 16 }}>No stocks match these filters.</td></tr>
                ) : (
                  filtered.map((r) => (
                    <tr
                      key={r.symbol}
                      className="wk-click"
                      title="Open the chart"
                      onClick={(e) => {
                        // the whole row opens the chart (2026-11-23); the Chart button keeps working on its own
                        if ((e.target as HTMLElement).closest("button, a, input")) return;
                        (e.currentTarget.querySelector("button.cup-chart-btn") as HTMLButtonElement | null)?.click();
                      }}
                    >
                      <td className="symbol-cell">
                        <span className="wk-logo"><StockLogo symbol={r.symbol} /></span>
                        <b>{r.symbol}</b>
                        <InstrumentBadge type={r.instrument_type} />
                        {(r.sectors ?? []).map((sc) => <span key={sc.key} className="vb-sec vb-sec-strong" style={{ marginLeft: 6 }}>{sc.label}</span>)}
                      </td>
                      <td>{r.company_name ?? "—"}</td>
                      <td>{r.instrument_type ?? "—"}</td>
                      <td><span className={statusChipClass(r.status)}>{statusLabel(r.status)}</span></td>
                      <td>
                        {r.status_group ? GROUP_LABELS[r.status_group] : "—"}
                        {!!r.targets_crossed && <span className="chip chip-pass" style={{ marginLeft: 6 }}>Target {r.targets_crossed} paar</span>}
                      </td>
                      <td className="num-cell">{fmtPrice(r.current_price ?? r.latest_monthly_close)}</td>
                      <td className="num-cell">{fmtPrice(r.neckline ?? r.potential_breakout_level)}</td>
                      <td className="num-cell">{fmtPct(r.distance_to_breakout_percent)}</td>
                      <td className="num-cell">{fmtPrice(r.entry_price)}</td>
                      <td className="num-cell">{fmtPrice(r.stop_loss)}</td>
                      <td className="num-cell">{fmtPrice(r.target_1)}</td>
                      <td className="num-cell">{fmtPrice(r.target_2)}</td>
                      <td className="num-cell">{fmtPrice(r.target_3)}</td>
                      <td>{fmtDay(r.cup_start_date ?? r.left_rim_date)}</td>
                      <td className="num-cell">{r.cup_age_years !== null ? `${r.cup_age_years.toFixed(1)}Y` : "—"}</td>
                      <td className="num-cell">{fmtPct(r.cup_depth_percent)}</td>
                      <td className="num-cell">{fmtPct(r.recovery_percent)}</td>
                      <td className="num-cell">{r.breakout_percent !== null ? fmtPct(r.breakout_percent, true) : "—"}</td>
                      <td>
                        <button
                          type="button"
                          className="secondary-button cup-chart-btn"
                          onClick={() =>
                            openCupChart(r)
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
          <div className="logo-line" style={{ fontWeight: 600, fontSize: "1.1rem" }}><span className="wk-logo"><StockLogo symbol={result.symbol} /></span>{result.symbol}</div>
          <div className="muted small">{metric(result)}</div>
        </>
      ) : (
        <div className="muted small">—</div>
      )}
    </div>
  );
}
