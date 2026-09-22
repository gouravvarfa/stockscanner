import { useEffect, useMemo, useState } from "react";
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

// PRD Forming is its own tab (placed right after PRD) but is deliberately NOT one
// of the six strategies in STRATEGY_NAMES, so summary cards / totals stay exactly as before.
type TabName = StrategyName | "PRD Forming";
const TAB_NAMES: TabName[] = ["Strategy One", "GFS", "Advanced GFS", "PRD", "PRD Forming", "NRD", "Value Buy"];

type SortKey = "symbol" | "daily_rsi" | "weekly_rsi" | "monthly_rsi" | "score" | "price";

const PAGE_SIZE = 10;

function fmt(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined || Number.isNaN(value) ? "N/A" : value.toFixed(digits);
}

interface FormingSetup {
  timeframe: string;
  a_date: string;
  a_low: number;
  a_rsi: number;
  b_date: string;
  b_low: number;
  b_rsi: number;
  ab_distance: number;
}

// A PRD Forming signal is a PRD-strategy signal that has not qualified yet
// (qualifies === false) but carries its developing A/B setups in extra.forming.
function isPrdForming(signal: StrategySignal): boolean {
  return signal.strategy === "PRD" && !signal.qualifies;
}

function formingOf(signal: StrategySignal): FormingSetup[] {
  const f = signal.extra.forming;
  return Array.isArray(f) ? (f as FormingSetup[]) : [];
}

function timeframesOf(signal: StrategySignal): string[] {
  if (isPrdForming(signal)) return Array.from(new Set(formingOf(signal).map((f) => String(f.timeframe).toUpperCase())));
  const tf = signal.extra.divergence_timeframes;
  return Array.isArray(tf) ? (tf as string[]) : [];
}

interface PrdDetail {
  status: "PRD_CONFIRMED" | "PRD_FORMING";
  a_date: string | null;
  a_price: number | null;
  b_date: string | null;
  b_price: number | null;
  distance: number | null;
}

// Same A/B facts for both states, read from whichever structure the backend
// attached (extra.forming for developing setups, extra.divergences for confirmed).
function prdDetail(signal: StrategySignal): PrdDetail | null {
  if (isPrdForming(signal)) {
    const f = formingOf(signal)[0];
    if (!f) return null;
    return { status: "PRD_FORMING", a_date: f.a_date, a_price: f.a_low, b_date: f.b_date, b_price: f.b_low, distance: f.ab_distance };
  }
  const d = (Array.isArray(signal.extra.divergences) ? signal.extra.divergences[0] : null) as Record<string, unknown> | null;
  if (!d) return null;
  const num = (v: unknown) => (typeof v === "number" ? v : null);
  const str = (v: unknown) => (v == null ? null : String(v));
  const a = num(d.swing1_bar);
  const b = num(d.swing2_bar);
  return {
    status: "PRD_CONFIRMED",
    a_date: str(d.a_date ?? d.swing1_date),
    a_price: num(d.a_low ?? d.swing1_price),
    b_date: str(d.b_date ?? d.swing2_date),
    b_price: num(d.b_low ?? d.swing2_price),
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
  if (isPrdForming(signal)) {
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
      {leg.fresh ? "🔥 Fresh" : ""} — {leg.bars_ago} bar{leg.bars_ago === 1 ? "" : "s"} ago
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

  const isPrdTab = activeStrategy === "PRD" || activeStrategy === "PRD Forming";
  const isDivergenceTab = isPrdTab || activeStrategy === "NRD";
  const signalsForActive: StrategySignal[] = latest?.strategies?.[activeStrategy] ?? [];

  const richBySymbol = useMemo(() => {
    const map = new Map<string, StockResult>();
    for (const r of latest?.top10 ?? []) map.set(r.symbol, r);
    return map;
  }, [latest]);

  const totalSignals = useMemo(() => {
    if (!latest) return 0;
    return STRATEGY_NAMES.reduce((sum, name) => sum + (latest.strategies?.[name]?.length ?? 0), 0);
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

  function sortBy(key: SortKey) {
    if (key === sortKey) setAsc(!asc);
    else {
      setSortKey(key);
      setAsc(true);
    }
  }

  const columnCount = isDivergenceTab ? (isPrdTab ? 13 : 10) : activeStrategy === "Strategy One" ? 8 : activeStrategy === "Value Buy" ? 7 : 7;

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Dashboard</h1>
          <p className="page-subtitle">Quick overview of all active signals and market insights</p>
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          <button className="primary-button" onClick={runScan} disabled={scanning}>
            {scanning ? "Scanning A Group…" : "Run Scan"}
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
                Scanning{progress.currentSymbol ? `: ${progress.currentSymbol}` : "…"}
              </span>
              <span>
                {progress.processed} / {progress.total || "?"} ({progress.percentage.toFixed(1)}%)
              </span>
            </div>
            <div className="active-scan-bar">
              <div className="active-scan-bar-fill" style={{ width: `${Math.min(progress.percentage, 100)}%` }} />
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

      {latest && (
        <div className="scan-meta card">
          <div>
            Data as of <strong>{new Date(latest.finished_at).toLocaleString()}</strong>
          </div>
          <div>
            A Group universe: {latest.universe_returned}/{latest.universe_requested} (all strategies)
          </div>
          <div>Stocks scanned: {latest.stocks_scanned} · failed: {latest.stocks_failed}</div>
          <div>Execution time: {latest.execution_seconds.toFixed(1)}s</div>
        </div>
      )}

      {!latest && !scanning && !scanError && (
        <div className="card state-block">
          <div className="state-icon">📊</div>
          <div className="state-title">No signals found</div>
          <div className="state-subtitle">Run a scan to populate the dashboard with live A Group signals.</div>
        </div>
      )}

      {latest && (
        <>
          <div className="summary-grid">
            <div className="summary-card">
              <div className="summary-card-top">
                <span className="summary-icon summary-icon-accent">Σ</span>
                <span className="summary-label">Total Signals</span>
              </div>
              <span className="summary-value">{totalSignals}</span>
            </div>
          </div>

          {/* All 6 active strategies, driven entirely from latest.strategies
              (real backend counts) — no hardcoded values. Previously this
              grid only surfaced PRD/NRD/Value Buy; System One/GFS/Advanced
              GFS had no summary card even though the data was already
              present in the API response. */}
          <div className="summary-grid strategy-summary-grid">
            {STRATEGY_NAMES.map((name) => {
              const count = latest.strategies?.[name]?.length ?? 0;
              const breakdown =
                name === "PRD" ? prdBreakdown : name === "NRD" ? nrdBreakdown : null;
              return (
                <div className="summary-card" key={name}>
                  <div className="summary-card-top">
                    <span className="summary-label">{strategyDisplayName(name)}</span>
                  </div>
                  <span className="summary-value">{count}</span>
                  {breakdown && (
                    <span className="summary-breakdown">
                      Daily: <b>{breakdown.daily}</b> | Weekly: <b>{breakdown.weekly}</b> | Monthly:{" "}
                      <b>{breakdown.monthly}</b>
                    </span>
                  )}
                </div>
              );
            })}
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
                  : name === "PRD Forming"
                    ? "PRD Forming"
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
                    {isPrdTab && <th>Status</th>}
                    {isPrdTab && <th>A (date · low)</th>}
                    {isPrdTab && <th>B / Current (date · price)</th>}
                    <th>Signal Date</th>
                    {isDivergenceTab ? (
                      <>
                        <th>{isPrdTab ? "A RSI" : "RSI Leg 1"}</th>
                        <th>{isPrdTab ? "B / Current RSI" : "RSI Leg 2"}</th>
                        <th>{isPrdTab ? "Candle Distance" : "Bars Ago"}</th>
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
                      const detail = isPrdTab ? prdDetail(s) : null;
                      const tfs = timeframesOf(s);
                      const leg = bestDivergenceLeg(s);
                      const price = s.extra.current_price as number | undefined;
                      const source = s.extra.data_source as string | undefined;
                      return (
                        <tr key={`${s.strategy}-${s.qualifies ? "c" : "f"}-${s.symbol}-${rowIndex}`} onClick={() => setSelected(s)} className="clickable-row">
                          <td className="symbol-cell">{s.symbol}<InstrumentBadge type={s.instrument_type} /></td>
                          {isDivergenceTab && (
                            <td>
                              <span className={`divergence-badge divergence-badge-${(isPrdTab ? "prd" : activeStrategy).toLowerCase()}`}>
                                {isPrdTab ? "PRD" : activeStrategy}
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
                          {isPrdTab && (
                            <>
                              <td>
                                <span className={detail?.status === "PRD_FORMING" ? "chip" : "chip chip-pass"}>
                                  {detail?.status === "PRD_FORMING" ? "PRD FORMING" : "PRD CONFIRMED"}
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
                                {isPrdTab && detail?.distance != null ? (
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
