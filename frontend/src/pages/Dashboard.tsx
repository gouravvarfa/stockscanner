import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { STRATEGY_NAMES, strategyDisplayName, type StockResult, type StrategyName, type StrategySignal } from "../services/api";
import { TopRankedCandidates } from "../components/TopRankedCandidates";
import { useChart } from "../chart/ChartContext";
import { useScan } from "../context/ScanContext";
import { BestStockCard } from "../components/BestStockCard";
import { StockDetailPanel } from "../components/StockDetailPanel";
import { ConditionChip } from "../components/ConditionChip";
import { SourceBadge } from "../components/SourceBadge";
import { InstrumentBadge } from "../components/InstrumentBadge";
import { FilterIcon } from "../components/icons";
import { ChartBarIcon } from "../components/icons";

// PRD Forming / NRD Forming are their own tabs (placed right after PRD / NRD)
// but are deliberately NOT among the six strategies in STRATEGY_NAMES, so
// summary cards / totals stay exactly as before.
type TabName = StrategyName | "PRD Forming" | "NRD Forming";
// Value Buy is not on the Dashboard any more: it has its own page over the whole A Group (2026-11-22).
const TAB_NAMES: TabName[] = [
  "Strategy One", "GFS", "Advanced GFS", "50 GFS", "PRD", "PRD Forming", "NRD", "NRD Forming",
];
const DASHBOARD_STRATEGIES = STRATEGY_NAMES.filter((name) => name !== "Value Buy");

type SortKey = "symbol" | "daily_rsi" | "weekly_rsi" | "monthly_rsi" | "score" | "price";

const PAGE_SIZE = 10;

function fmt(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined || Number.isNaN(value) ? "N/A" : value.toFixed(digits);
}

interface FormingSetup {
  timeframe: string;
  a_date: string;
  a_low?: number; // PRD Forming (price higher low)
  a_high?: number; // NRD Forming (price lower high)
  a_rsi: number;
  b_date: string;
  b_low?: number;
  b_high?: number;
  b_rsi: number;
  ab_distance: number;
}

// A PRD/NRD Forming signal is a PRD/NRD-strategy signal that has not
// qualified yet (qualifies === false) but carries its developing A/B setups
// in extra.forming.
function isFormingSignal(signal: StrategySignal): boolean {
  return (signal.strategy === "PRD" || signal.strategy === "NRD") && !signal.qualifies;
}

function formingOf(signal: StrategySignal): FormingSetup[] {
  const f = signal.extra.forming;
  return Array.isArray(f) ? (f as FormingSetup[]) : [];
}

function timeframesOf(signal: StrategySignal): string[] {
  if (isFormingSignal(signal)) return Array.from(new Set(formingOf(signal).map((f) => String(f.timeframe).toUpperCase())));
  const tf = signal.extra.divergence_timeframes;
  return Array.isArray(tf) ? (tf as string[]) : [];
}

interface DivergenceDetail {
  status: "PRD_CONFIRMED" | "PRD_FORMING" | "NRD_CONFIRMED" | "NRD_FORMING";
  a_date: string | null;
  a_price: number | null;
  b_date: string | null;
  b_price: number | null;
  distance: number | null;
}

// Same A/B facts for both states and both strategies, read from whichever
// structure the backend attached (extra.forming for developing setups,
// extra.divergences for confirmed). PRD legs are price lows (a_low/b_low),
// NRD legs are price highs (a_high/b_high) — both read here generically.
function divergenceDetail(signal: StrategySignal): DivergenceDetail | null {
  const isNrd = signal.strategy === "NRD";
  if (isFormingSignal(signal)) {
    const f = formingOf(signal)[0];
    if (!f) return null;
    return {
      status: isNrd ? "NRD_FORMING" : "PRD_FORMING",
      a_date: f.a_date, a_price: f.a_low ?? f.a_high ?? null,
      b_date: f.b_date, b_price: f.b_low ?? f.b_high ?? null,
      distance: f.ab_distance,
    };
  }
  const d = (Array.isArray(signal.extra.divergences) ? signal.extra.divergences[0] : null) as Record<string, unknown> | null;
  if (!d) return null;
  const num = (v: unknown) => (typeof v === "number" ? v : null);
  const str = (v: unknown) => (v == null ? null : String(v));
  const a = num(d.swing1_bar);
  const b = num(d.swing2_bar);
  return {
    status: isNrd ? "NRD_CONFIRMED" : "PRD_CONFIRMED",
    a_date: str(d.a_date ?? d.swing1_date),
    a_price: num(d.a_low ?? d.a_high ?? d.swing1_price),
    b_date: str(d.b_date ?? d.swing2_date),
    b_price: num(d.b_low ?? d.b_high ?? d.swing2_price),
    distance: a !== null && b !== null ? b - a : null,
  };
}

function fmtDay(v: string | null | undefined): string {
  return v ? String(v).slice(0, 10) : "—";
}

interface DivergenceLeg {
  rsi1: number | null;
  rsi2: number | null;
  bars_ago: number | null;
  fresh: boolean;
}

// The backend (backend/strategies/prd.py / nrd.py) sorts `extra.divergences`
// freshest-first and only ever includes entries that already passed the
// leg-RSI + 7-bar freshness + (PRD only) candle-confirmation checks — so
// the first entry is always the one that qualified this signal.
function bestDivergenceLeg(signal: StrategySignal): DivergenceLeg | null {
  if (isFormingSignal(signal)) {
    const f = formingOf(signal)[0];
    return f ? { rsi1: f.a_rsi, rsi2: f.b_rsi, bars_ago: 0, fresh: false } : null;
  }
  const divergences = signal.extra.divergences;
  if (!Array.isArray(divergences) || divergences.length === 0) return null;
  const best = divergences[0] as Record<string, unknown>;
  return {
    rsi1: typeof best.rsi1 === "number" ? best.rsi1 : null,
    rsi2: typeof best.rsi2 === "number" ? best.rsi2 : null,
    bars_ago: typeof best.bars_ago === "number" ? best.bars_ago : null,
    fresh: Boolean(best.fresh),
  };
}

function FreshnessBadge({ leg }: { leg: DivergenceLeg | null }) {
  if (!leg || leg.bars_ago === null) return <span className="muted small">—</span>;
  return (
    <span className={leg.fresh ? "chip chip-pass" : "muted small"}>
      {leg.fresh ? "Fresh" : ""} — {leg.bars_ago} bar{leg.bars_ago === 1 ? "" : "s"} ago
    </span>
  );
}

function countTimeframes(signals: StrategySignal[]): { daily: number; weekly: number; monthly: number } {
  const counts = { daily: 0, weekly: 0, monthly: 0 };
  for (const s of signals) {
    for (const tf of timeframesOf(s)) {
      if (tf === "DAILY") counts.daily++;
      else if (tf === "WEEKLY") counts.weekly++;
      else if (tf === "MONTHLY") counts.monthly++;
    }
  }
  return counts;
}

function SkeletonRows({ columns }: { columns: number }) {
  return (
    <>
      {[0, 1, 2, 3, 4].map((row) => (
        <tr key={row} className="skeleton-row">
          {Array.from({ length: columns }).map((_, col) => (
            <td key={col}>
              <div className="skeleton-bar" style={{ width: col === 0 ? "70%" : "50%" }} />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

export function Dashboard() {
  const {
    latest,
    scanning,
    scanError,
    scanIssueKind,
    runScan,
    runFreshScan,
    stopScan,
    progress,
    partial,
    cacheAgeSeconds,
    localRows,
  } = useScan();
  const { openChart } = useChart();

  const [activeStrategy, setActiveStrategy] = useState<TabName>("PRD");
  const [showFilters, setShowFilters] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>("symbol");
  const [asc, setAsc] = useState(true);
  const [sourceFilter, setSourceFilter] = useState<string>("all");
  const [timeframeFilter, setTimeframeFilter] = useState<string>("all");
  const [symbolSearch, setSymbolSearch] = useState("");
  const [page, setPage] = useState(1);

  useEffect(() => setPage(1), [activeStrategy, sourceFilter, timeframeFilter, symbolSearch]);

  // A/B + Status columns: PRD's confirmed/forming tabs, and NRD Forming (NRD's
  // confirmed tab keeps its original simpler RSI-leg/bars-ago columns).
  const isAbTab = activeStrategy === "PRD" || activeStrategy === "PRD Forming" || activeStrategy === "NRD Forming";
  const abBadgeLabel = activeStrategy === "NRD Forming" ? "NRD" : "PRD";
  const abPriceLabel = activeStrategy === "NRD Forming" ? "high" : "low";
  const isDivergenceTab = isAbTab || activeStrategy === "NRD";
  const signalsForActive: StrategySignal[] = latest?.strategies?.[activeStrategy] ?? [];

  const richBySymbol = useMemo(() => {
    const map = new Map<string, StockResult>();
    for (const r of latest?.top10 ?? []) map.set(r.symbol, r);
    return map;
  }, [latest]);

  const totalSignals = useMemo(() => {
    if (!latest) return 0;
    return DASHBOARD_STRATEGIES.reduce((sum, name) => sum + (latest.strategies?.[name]?.length ?? 0), 0);
  }, [latest]);

  const prdSignals = useMemo(() => latest?.strategies?.["PRD"] ?? [], [latest]);
  const nrdSignals = useMemo(() => latest?.strategies?.["NRD"] ?? [], [latest]);
  const prdBreakdown = useMemo(() => countTimeframes(prdSignals), [prdSignals]);
  const nrdBreakdown = useMemo(() => countTimeframes(nrdSignals), [nrdSignals]);

  const sources = useMemo(() => {
    const set = new Set(signalsForActive.map((s) => String(s.extra.data_source ?? "")).filter(Boolean));
    return ["all", ...Array.from(set).sort()];
  }, [signalsForActive]);

  const [selected, setSelected] = useState<StrategySignal | null>(null);

  const filtered = useMemo(() => {
    let rows = signalsForActive;
    if (sourceFilter !== "all") rows = rows.filter((s) => s.extra.data_source === sourceFilter);
    if (isDivergenceTab && timeframeFilter !== "all") {
      rows = rows.filter((s) => timeframesOf(s).includes(timeframeFilter));
    }
    if (symbolSearch.trim()) {
      const q = symbolSearch.trim().toUpperCase();
      rows = rows.filter((s) => s.symbol.toUpperCase().includes(q));
    }

    const sorted = [...rows];
    sorted.sort((a, b) => {
      let av: number | string;
      let bv: number | string;
      if (sortKey === "symbol") {
        av = a.symbol;
        bv = b.symbol;
        return asc ? av.localeCompare(bv) : bv.localeCompare(av);
      }
      if (sortKey === "score") {
        av = (a.extra.score as number | undefined) ?? -Infinity;
        bv = (b.extra.score as number | undefined) ?? -Infinity;
      } else if (sortKey === "price") {
        av = (a.extra.current_price as number | undefined) ?? -Infinity;
        bv = (b.extra.current_price as number | undefined) ?? -Infinity;
      } else {
        av = a[sortKey] ?? -Infinity;
        bv = b[sortKey] ?? -Infinity;
      }
      return asc ? (av as number) - (bv as number) : (bv as number) - (av as number);
    });
    return sorted;
  }, [signalsForActive, sourceFilter, timeframeFilter, symbolSearch, sortKey, asc, isDivergenceTab]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pageRows = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
  // Identity-based row keys (not position-based): re-sorting or a new
  // result arriving must not remount — and re-animate — every row.
  const pageRowKeys = (() => {
    const seen = new Map<string, number>();
    return pageRows.map((s) => {
      const base = `${s.strategy}-${s.qualifies ? "c" : "f"}-${s.symbol}`;
      const n = seen.get(base) ?? 0;
      seen.set(base, n + 1);
      return n === 0 ? base : `${base}-${n}`;
    });
  })();

  function sortBy(key: SortKey) {
    if (key === sortKey) setAsc(!asc);
    else {
      setSortKey(key);
      setAsc(true);
    }
  }

  const columnCount = isDivergenceTab ? (isAbTab ? 13 : 10) : activeStrategy === "Strategy One" ? 8 : activeStrategy === "Value Buy" ? 7 : 7;

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Dashboard</h1>
          <p className="page-subtitle">
            Setups in the stocks of today&apos;s STRONG sectors only (sector index daily, weekly and monthly RSI above 60)
          </p>
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          <button className="primary-button" onClick={runScan} disabled={scanning}>
            {scanning ? "Scanning strong sectors…" : "Run Scan"}
          </button>
          {!scanning && (
            <button className="secondary-button" onClick={runFreshScan} title="Ignore cache, fetch fresh Angel One data">
              Fresh Scan
            </button>
          )}
          {scanning && (
            <button className="secondary-button stop-scan-button" onClick={stopScan} title="Stop the running scan">
              Stop Scan
            </button>
          )}
        </div>
      </div>

      {scanning && progress && (
        <div className="card scan-meta" style={{ marginBottom: 12 }}>
          <div style={{ width: "100%" }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 6 }}>
              <span>
                {progress.total === 0 && progress.processed === 0
                  ? "Finding today's STRONG sectors…"
                  : `Scanning${progress.currentSymbol ? `: ${progress.currentSymbol}` : "…"}`}
              </span>
              <span>
                {progress.processed} / {progress.total || "?"} ({progress.percentage.toFixed(1)}%)
              </span>
            </div>
            <div className="active-scan-bar">
              <div className="active-scan-bar-fill" style={{ transform: `scaleX(${Math.min(progress.percentage, 100) / 100})` }} />
            </div>
            <div style={{ fontSize: 12, opacity: 0.7, marginTop: 6 }}>
              Signals found {progress.signalsFound} · Failed {progress.failed} · Elapsed {Math.floor(progress.elapsedSeconds / 60)}m {Math.round(progress.elapsedSeconds % 60)}s · ETA{" "}
              {progress.etaSeconds === null ? "Estimating…" : `${Math.floor(progress.etaSeconds / 60)}m ${Math.round(progress.etaSeconds % 60)}s`}
            </div>
            {partial.length > 0 && (
              <div className="live-results" title="Stocks that already qualified — updates as each stock finishes">
                {partial.slice(-40).map((p) => (
                  <span key={p.seq} className="live-result-chip">
                    {p.symbol}
                    <InstrumentBadge type={p.instrument_type} /> · {p.strategies.join(", ")}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {!scanning && cacheAgeSeconds !== null && (
        <p style={{ fontSize: 12, opacity: 0.7, marginTop: -6, marginBottom: 12 }}>
          Cached data — age {Math.floor(cacheAgeSeconds / 3600)}h {Math.floor((cacheAgeSeconds % 3600) / 60)}m
        </p>
      )}

      {scanError && !scanning && scanIssueKind === "interrupted" && (
        <div className="notice-banner">
          <div>
            <strong>Backend restarted — previous scan was interrupted.</strong> Nothing to retry for that scan; start
            a new one whenever you're ready.
            {localRows.length > 0 && (
              <>
                {" "}
                {localRows.length} stock{localRows.length === 1 ? "" : "s"} from that scan are still saved on this
                device — see <a href="/history">Scan History</a>.
              </>
            )}
          </div>
        </div>
      )}
      {/* Genuinely no usable data AND the backend is unreachable — the only
          time this shows the hard red error, per the "local data first"
          rule: if this device already has saved results, that's shown
          instead (below), never blanked out just because Render is down. */}
      {scanError && !scanning && scanIssueKind !== "interrupted" && localRows.length === 0 && (
        <div className="error-banner">
          <div>
            <strong>Unable to load scanner data.</strong> {scanError}
          </div>
          <button className="secondary-button" onClick={runScan}>
            Retry
          </button>
        </div>
      )}
      {scanError && !scanning && scanIssueKind !== "interrupted" && localRows.length > 0 && (
        <div className="notice-banner">
          <div>
            <strong>Backend unavailable right now.</strong> Showing {localRows.length} stock
            {localRows.length === 1 ? "" : "s"} already saved on this device —{" "}
            <a href="/history">see Scan History</a>. Trying to reconnect automatically.
          </div>
        </div>
      )}
      {scanError && scanning && (
        <p className="muted small" style={{ marginTop: -8, marginBottom: 12 }}>
          {scanError}
        </p>
      )}

      {!latest && !scanning && !scanError && (
        <div className="card state-block">
          <div className="state-icon"><ChartBarIcon width={28} height={28} /></div>
          <div className="state-title">No signals found</div>
          <div className="state-subtitle">
            Run a scan: it finds today&apos;s STRONG sectors and checks every setup on their stocks.
          </div>
        </div>
      )}

      {latest && (
        <div className="card dash-strong">
          <div className="dash-strong-head">
            <strong>Today&apos;s strong sectors</strong>
            <span className="muted small">
              Daily, weekly and monthly RSI of the sector index all above 60 · from the Weekly Sectors rule
            </span>
          </div>
          {(latest.strong_sectors ?? []).length === 0 ? (
            <p className="muted small" style={{ margin: "6px 0 0" }}>
              No sector is STRONG right now, so there were no stocks to scan. See <Link to="/weekly-sectors">Weekly Sectors</Link>.
            </p>
          ) : (
            <div className="dash-strong-list">
              {(latest.strong_sectors ?? []).map((s) => (
                <span key={s.key} className="dash-strong-chip" title={s.index}>
                  <b>{s.label}</b> · {s.stocks} stocks · RSI {[s.rsi.d, s.rsi.w, s.rsi.m].map((v) => (v === null ? "n/a" : v.toFixed(0))).join("/")}
                </span>
              ))}
            </div>
          )}
          <p className="muted small" style={{ margin: "10px 0 0" }}>
            Data as of <b>{new Date(latest.finished_at).toLocaleString("en-IN")}</b> · {latest.stocks_scanned} stocks scanned
            {latest.stocks_failed ? ` · ${latest.stocks_failed} failed` : ""} · {latest.execution_seconds.toFixed(0)}s · Value Buy has its
            own page: <Link to="/value-buy">open Value Buy</Link>
          </p>
        </div>
      )}

      {latest && (
        <>
          {/* Every setup's count from latest.strategies (real backend counts); a tile opens its tab below. */}
          <div className="card">
            <div className="dash-tiles">
              <div className="tb-summary-tile dash-tile-total">
                <div className="tb-summary-label">TOTAL SIGNALS</div>
                <div className="tb-summary-value">{totalSignals}</div>
                <div className="tb-config-hint" style={{ margin: 0 }}>in the strong sectors</div>
              </div>
              {DASHBOARD_STRATEGIES.map((name) => {
                const count = latest.strategies?.[name]?.length ?? 0;
                const breakdown = name === "PRD" ? prdBreakdown : name === "NRD" ? nrdBreakdown : null;
                return (
                  <button
                    type="button"
                    key={name}
                    className={`tb-summary-tile dash-tile${activeStrategy === name ? " active" : ""}`}
                    onClick={() => setActiveStrategy(name)}
                    title={`Show the ${strategyDisplayName(name)} signals`}
                  >
                    <div className="tb-summary-label">{strategyDisplayName(name).toUpperCase()}</div>
                    <div className={`tb-summary-value${count ? " wk-up" : ""}`}>{count}</div>
                    <div className="tb-config-hint" style={{ margin: 0 }}>
                      {breakdown ? `D ${breakdown.daily} · W ${breakdown.weekly} · M ${breakdown.monthly}` : count === 1 ? "stock" : "stocks"}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          <TopRankedCandidates refreshKey={latest.finished_at} />

          {activeStrategy === "Strategy One" && <BestStockCard stock={latest.best} />}

          <div className="tabs">
            {TAB_NAMES.map((name) => (
              <button
                key={name}
                className={activeStrategy === name ? "tab active" : "tab"}
                onClick={() => setActiveStrategy(name)}
              >
                {name === "PRD" || name === "NRD"
                  ? `${name} Signals`
                  : name === "PRD Forming" || name === "NRD Forming"
                    ? name
                    : strategyDisplayName(name)}
                <span className="tab-count">{latest.strategies?.[name]?.length ?? 0}</span>
              </button>
            ))}
          </div>

          <div className="filter-toggle-row">
            <button className="secondary-button" onClick={() => setShowFilters((v) => !v)}>
              <FilterIcon style={{ verticalAlign: -3, marginRight: 6 }} />
              Filter
            </button>
          </div>

          {showFilters && (
            <div className="card filters-row filter-panel">
              {isDivergenceTab && (
                <label>
                  Timeframe
                  <select value={timeframeFilter} onChange={(e) => setTimeframeFilter(e.target.value)}>
                    <option value="all">All timeframes</option>
                    <option value="DAILY">Daily</option>
                    <option value="WEEKLY">Weekly</option>
                    <option value="MONTHLY">Monthly</option>
                  </select>
                </label>
              )}
              <label>
                Data Source
                <select value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)}>
                  {sources.map((s) => (
                    <option key={s} value={s}>
                      {s === "all" ? "All sources" : s}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Search symbol
                <input type="text" value={symbolSearch} onChange={(e) => setSymbolSearch(e.target.value)} placeholder="e.g. RELIANCE" />
              </label>
            </div>
          )}

          {!scanning && signalsForActive.length === 0 ? (
            <div className="card state-block">
              <div className="state-title">No signals found</div>
              <div className="state-subtitle">No stocks currently qualify for {activeStrategy} in this scan.</div>
            </div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th onClick={() => sortBy("symbol")}>Symbol</th>
                    {isDivergenceTab && <th>Divergence Type</th>}
                    {isDivergenceTab && <th>Timeframe</th>}
                    {isAbTab && <th>Status</th>}
                    {isAbTab && <th>A (date · {abPriceLabel})</th>}
                    {isAbTab && <th>B / Current (date · price)</th>}
                    <th>Signal Date</th>
                    {isDivergenceTab ? (
                      <>
                        <th>{isAbTab ? "A RSI" : "RSI Leg 1"}</th>
                        <th>{isAbTab ? "B / Current RSI" : "RSI Leg 2"}</th>
                        <th>{isAbTab ? "Candle Distance" : "Bars Ago"}</th>
                      </>
                    ) : (
                      <>
                        <th onClick={() => sortBy("daily_rsi")}>Daily RSI</th>
                        <th onClick={() => sortBy("weekly_rsi")}>Weekly RSI</th>
                        <th onClick={() => sortBy("monthly_rsi")}>Monthly RSI</th>
                      </>
                    )}
                    {activeStrategy === "Strategy One" && <th onClick={() => sortBy("score")}>Score</th>}
                    {activeStrategy === "Value Buy" && <th>Conditions</th>}
                    <th onClick={() => sortBy("price")} className="num-cell">Price</th>
                    <th>Data Source</th>
                    <th>Chart</th>
                  </tr>
                </thead>
                <tbody>
                  {scanning ? (
                    <SkeletonRows columns={columnCount} />
                  ) : (
                    pageRows.map((s, rowIndex) => {
                      const detail = isAbTab ? divergenceDetail(s) : null;
                      const tfs = timeframesOf(s);
                      const leg = bestDivergenceLeg(s);
                      const price = s.extra.current_price as number | undefined;
                      const source = s.extra.data_source as string | undefined;
                      const isForming = Boolean(detail?.status.endsWith("_FORMING"));
                      return (
                        <tr key={pageRowKeys[rowIndex]} onClick={() => setSelected(s)} className="clickable-row">
                          <td className="symbol-cell">{s.symbol}<InstrumentBadge type={s.instrument_type} />{typeof s.extra.sector === "string" && s.extra.sector && <span className="sector-chip">{s.extra.sector}</span>}</td>
                          {isDivergenceTab && (
                            <td>
                              <span className={`divergence-badge divergence-badge-${(isAbTab ? abBadgeLabel : activeStrategy).toLowerCase()}`}>
                                {isAbTab ? abBadgeLabel : activeStrategy}
                              </span>
                            </td>
                          )}
                          {isDivergenceTab && (
                            <td>
                              {tfs.length > 0 ? (
                                <span className="timeframe-chip">{tfs.join(" + ")}</span>
                              ) : (
                                "—"
                              )}
                            </td>
                          )}
                          {isAbTab && (
                            <>
                              <td>
                                <span className={isForming ? "chip" : "chip chip-pass"}>
                                  {isForming ? `${abBadgeLabel} FORMING` : `${abBadgeLabel} CONFIRMED`}
                                </span>
                              </td>
                              <td>{detail ? `${fmtDay(detail.a_date)} · ${fmt(detail.a_price, 2)}` : "—"}</td>
                              <td>{detail ? `${fmtDay(detail.b_date)} · ${fmt(detail.b_price, 2)}` : "—"}</td>
                            </>
                          )}
                          <td>{s.signal_date ? new Date(s.signal_date).toLocaleDateString() : "N/A"}</td>
                          {isDivergenceTab ? (
                            <>
                              <td className="num-cell">{fmt(leg?.rsi1 ?? null)}</td>
                              <td className="num-cell">{fmt(leg?.rsi2 ?? null)}</td>
                              <td>
                                {isAbTab && detail?.distance != null ? (
                                  <span className="muted small">{detail.distance} candles</span>
                                ) : (
                                  <FreshnessBadge leg={leg} />
                                )}
                              </td>
                            </>
                          ) : (
                            <>
                              <td className="num-cell">{fmt(s.daily_rsi)}</td>
                              <td className="num-cell">{fmt(s.weekly_rsi)}</td>
                              <td className="num-cell">{fmt(s.monthly_rsi)}</td>
                            </>
                          )}
                          {activeStrategy === "Strategy One" && (
                            <td className="num-cell">{fmt(s.extra.score as number | undefined)}</td>
                          )}
                          {activeStrategy === "Value Buy" && (
                            <td>
                              <div className="chip-row">
                                {Object.entries(s.conditions).map(([k, v]) => (
                                  <ConditionChip key={k} label={k} passed={v} />
                                ))}
                              </div>
                            </td>
                          )}
                          <td className="num-cell">{price !== undefined ? `₹${price.toFixed(2)}` : "—"}</td>
                          <td>
                            <SourceBadge source={source} />
                          </td>
                          <td>
                            <button
                              type="button"
                              className="secondary-button"
                              onClick={(e) => {
                                e.stopPropagation();
                                openChart(s.symbol, {
                                  strategy: s.strategy,
                                  daily_rsi: s.daily_rsi,
                                  weekly_rsi: s.weekly_rsi,
                                  monthly_rsi: s.monthly_rsi,
                                  signal_date: s.signal_date,
                                  divergence_timeframe: tfs.length > 0 ? tfs.join(" + ") : null,
                                  explanation: s.explanation,
                                });
                              }}
                            >
                              Chart
                            </button>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
              {!scanning && filtered.length > 0 && (
                <div className="table-pagination">
                  <span>
                    Showing {(currentPage - 1) * PAGE_SIZE + 1}–{Math.min(currentPage * PAGE_SIZE, filtered.length)} of{" "}
                    {filtered.length} signals
                  </span>
                  <div className="pagination-controls">
                    <button disabled={currentPage === 1} onClick={() => setPage(currentPage - 1)}>
                      Previous
                    </button>
                    {Array.from({ length: totalPages }, (_, i) => i + 1)
                      .slice(Math.max(0, currentPage - 3), Math.max(0, currentPage - 3) + 5)
                      .map((p) => (
                        <button key={p} className={p === currentPage ? "active" : ""} onClick={() => setPage(p)}>
                          {p}
                        </button>
                      ))}
                    <button disabled={currentPage === totalPages} onClick={() => setPage(currentPage + 1)}>
                      Next
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}

      {selected && (
        <StockDetailPanel signal={selected} richData={richBySymbol.get(selected.symbol) ?? null} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
