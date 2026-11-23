import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { STRATEGY_NAMES, strategyDisplayName, type StockResult, type StrategyName, type StrategySignal } from "../services/api";
import { TopRankedCandidates } from "../components/TopRankedCandidates";
import { useChart } from "../chart/ChartContext";
import { useScan } from "../context/ScanContext";
import { BestStockCard } from "../components/BestStockCard";
import { StockDetailPanel } from "../components/StockDetailPanel";
import { InstrumentBadge } from "../components/InstrumentBadge";
import { StockLogo } from "../components/StockLogo";
import { DashboardMotif, PageHero } from "../components/PageHero";
import { ChartBarIcon, TrendIcon } from "../components/icons";

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

// One date style on the whole page: "17 Nov 2026" (a plain YYYY-MM-DD is read as that calendar day, not UTC).
function fmtDate(v: string | null | undefined): string {
  if (!v) return "—";
  const s = String(v);
  const ymd = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  const d = ymd ? new Date(+ymd[1], +ymd[2] - 1, +ymd[3]) : new Date(s);
  return Number.isNaN(d.getTime())
    ? s.slice(0, 10)
    : d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

function fmtPrice(v: number | null | undefined): string {
  return v === null || v === undefined || Number.isNaN(v)
    ? "—"
    : `₹${v.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function ago(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const h = Math.floor(m / 60);
  const d = Math.floor(h / 24);
  return d > 0 ? `${d}d ${h % 24}h ago` : h > 0 ? `${h}h ${m % 60}m ago` : `${m}m ago`;
}

const TF_LABEL: Record<string, string> = { DAILY: "Daily", WEEKLY: "Weekly", MONTHLY: "Monthly" };

function tabLabel(name: TabName): string {
  if (name === "PRD" || name === "NRD") return `${name} Signals`;
  if (name === "PRD Forming" || name === "NRD Forming") return name;
  return strategyDisplayName(name);
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
  const when = leg.bars_ago === 0 ? "latest bar" : `${leg.bars_ago} bar${leg.bars_ago === 1 ? "" : "s"} ago`;
  return (
    <span className="dash-fresh">
      {leg.fresh && <span className="chip chip-pass">Fresh</span>}
      <span className="muted small">{when}</span>
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
    scanQueued,
  } = useScan();
  const { openChart } = useChart();

  const [activeStrategy, setActiveStrategy] = useState<TabName>("PRD");
  const [sortKey, setSortKey] = useState<SortKey>("symbol");
  const [asc, setAsc] = useState(true);
  const [timeframeFilter, setTimeframeFilter] = useState<string>("all");
  const [symbolSearch, setSymbolSearch] = useState("");
  const [page, setPage] = useState(1);

  useEffect(() => setPage(1), [activeStrategy, timeframeFilter, symbolSearch]);

  // A/B columns: PRD's confirmed/forming tabs, and NRD Forming (NRD's confirmed tab keeps its simpler
  // RSI-leg/bars-ago columns). The tab itself says PRD/NRD and confirmed/forming, so no column repeats it.
  const isAbTab = activeStrategy === "PRD" || activeStrategy === "PRD Forming" || activeStrategy === "NRD Forming";
  // a developing setup shows how far apart A and B are; a confirmed one shows how fresh it is
  const isFormingTab = activeStrategy === "PRD Forming" || activeStrategy === "NRD Forming";
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

  const [selected, setSelected] = useState<StrategySignal | null>(null);

  const filtered = useMemo(() => {
    let rows = signalsForActive;
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
  }, [signalsForActive, timeframeFilter, symbolSearch, sortKey, asc, isDivergenceTab]);

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

  // Stock | (Timeframe) | (A | B) | Signal date | 3 RSI-type columns | (Score) | Price | Chart
  const columnCount = (isDivergenceTab ? (isAbTab ? 10 : 8) : 7) + (activeStrategy === "Strategy One" ? 1 : 0);

  // a sortable column header: the active one shows its direction
  const sortTh = (key: SortKey, label: string, num = false) => (
    <th
      className={`dash-sort${num ? " num-cell" : ""}${sortKey === key ? " active" : ""}`}
      onClick={() => sortBy(key)}
      aria-sort={sortKey === key ? (asc ? "ascending" : "descending") : "none"}
    >
      {label}
      <span className="dash-sort-mark" aria-hidden="true">{sortKey === key ? (asc ? "▲" : "▼") : ""}</span>
    </th>
  );

  return (
    <div className="page">
      <PageHero
        tone="dash"
        eyebrow="Today · strong sectors only"
        title="Dashboard"
        subtitle="Setups in the stocks of today's strong sectors — sectors whose index RSI is above 60 on the daily, weekly and monthly charts."
        motif={<DashboardMotif />}
      >
        <div className="dash-actions">
          {!scanning && cacheAgeSeconds !== null && (
            <span className="dash-last-scan">Last scan {ago(cacheAgeSeconds)}</span>
          )}
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
      </PageHero>

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

      {scanQueued && (
        <div className="notice-banner queue-banner">
          <span>{scanQueued}</span>
          <button type="button" className="secondary-button" onClick={() => void stopScan()}>Cancel</button>
        </div>
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
        <section className="card dash-strong" aria-labelledby="dash-strong-title">
          <div className="dash-card-head">
            <div>
              <h2 id="dash-strong-title">Today&apos;s strong sectors</h2>
              <p className="muted small">Daily, weekly and monthly RSI of the sector index all above 60</p>
            </div>
            <span className="dash-card-meta">
              {latest.stocks_scanned} stocks scanned
              {latest.stocks_failed ? ` · ${latest.stocks_failed} failed` : ""} ·{" "}
              {new Date(latest.finished_at).toLocaleString("en-IN", {
                day: "2-digit",
                month: "short",
                hour: "numeric",
                minute: "2-digit",
              })}
            </span>
          </div>
          {(latest.strong_sectors ?? []).length === 0 ? (
            <p className="muted small" style={{ margin: 0 }}>
              No sector is STRONG right now, so there were no stocks to scan. See <Link to="/weekly-sectors">Weekly Sectors</Link>.
            </p>
          ) : (
            <div className="dash-strong-list">
              {(latest.strong_sectors ?? []).map((s) => (
                <span key={s.key} className="dash-strong-chip" title={s.index}>
                  <b>{s.label}</b>
                  <span className="dash-strong-sep">·</span>
                  {s.stocks} stocks
                  <span className="dash-strong-sep">·</span>
                  RSI {[s.rsi.d, s.rsi.w, s.rsi.m].map((v) => (v === null ? "n/a" : v.toFixed(0))).join(" / ")}
                </span>
              ))}
            </div>
          )}
          <p className="muted small dash-foot">
            Value Buy scans the whole A Group on its own page: <Link to="/value-buy">open Value Buy</Link>
          </p>
        </section>
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
                    <div className="tb-config-hint dash-tile-sub" style={{ margin: 0 }}>
                      {breakdown ? (
                        <span
                          className="dash-tf"
                          title={`Daily ${breakdown.daily} · Weekly ${breakdown.weekly} · Monthly ${breakdown.monthly}`}
                        >
                          D <b>{breakdown.daily}</b> · W <b>{breakdown.weekly}</b> · M <b>{breakdown.monthly}</b>
                        </span>
                      ) : count === 1 ? (
                        "stock"
                      ) : (
                        "stocks"
                      )}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          <TopRankedCandidates refreshKey={latest.finished_at} />

          {activeStrategy === "Strategy One" && <BestStockCard stock={latest.best} />}

          {/* Signals (2026-11-22 tidy-up): setup tabs, search and the table in one card. No columns that only repeat the
              tab (type, status) or are always the same (data source); one date style; the table fits the page. */}
          <section className="card dash-signals" aria-labelledby="dash-signals-title">
            <div className="dash-card-head">
              <div>
                <h2 id="dash-signals-title">Signals</h2>
                <p className="muted small">Every stock that qualified, by setup. Click a row for its details.</p>
              </div>
              <div className="dash-tools">
                {isDivergenceTab && (
                  <select
                    className="dash-input"
                    value={timeframeFilter}
                    onChange={(e) => setTimeframeFilter(e.target.value)}
                    aria-label="Timeframe"
                  >
                    <option value="all">All timeframes</option>
                    <option value="DAILY">Daily</option>
                    <option value="WEEKLY">Weekly</option>
                    <option value="MONTHLY">Monthly</option>
                  </select>
                )}
                <input
                  className="dash-input dash-search"
                  type="search"
                  value={symbolSearch}
                  onChange={(e) => setSymbolSearch(e.target.value)}
                  placeholder="Search symbol"
                  aria-label="Search symbol"
                />
              </div>
            </div>

            <div className="tabs dash-tabs" role="tablist" aria-label="Setup">
              {TAB_NAMES.map((name) => (
                <button
                  key={name}
                  type="button"
                  role="tab"
                  aria-selected={activeStrategy === name}
                  className={activeStrategy === name ? "tab active" : "tab"}
                  onClick={() => setActiveStrategy(name)}
                >
                  {tabLabel(name)}
                  <span className="tab-count">{latest.strategies?.[name]?.length ?? 0}</span>
                </button>
              ))}
            </div>

            {!scanning && signalsForActive.length === 0 ? (
              <p className="muted dash-empty">No stock qualifies for {tabLabel(activeStrategy)} in this scan.</p>
            ) : !scanning && filtered.length === 0 ? (
              <p className="muted dash-empty">No signal matches this search.</p>
            ) : (
              <>
                <div className="table-wrap">
                  <table className="dash-signal-table">
                    <thead>
                      <tr>
                        {sortTh("symbol", "Stock")}
                        {isDivergenceTab && <th>Timeframe</th>}
                        {isAbTab && <th>A ({abPriceLabel})</th>}
                        {isAbTab && <th>B / now</th>}
                        <th>Signal date</th>
                        {isDivergenceTab ? (
                          <>
                            <th className="num-cell">{isAbTab ? "A RSI" : "RSI leg 1"}</th>
                            <th className="num-cell">{isAbTab ? "B RSI" : "RSI leg 2"}</th>
                            <th>{isFormingTab ? "A to B" : "Freshness"}</th>
                          </>
                        ) : (
                          <>
                            {sortTh("daily_rsi", "Daily RSI", true)}
                            {sortTh("weekly_rsi", "Weekly RSI", true)}
                            {sortTh("monthly_rsi", "Monthly RSI", true)}
                          </>
                        )}
                        {activeStrategy === "Strategy One" && sortTh("score", "Score", true)}
                        {sortTh("price", "Price", true)}
                        <th aria-label="Chart" />
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
                          const sector = typeof s.extra.sector === "string" ? s.extra.sector : "";
                          return (
                            <tr key={pageRowKeys[rowIndex]} onClick={() => setSelected(s)} className="clickable-row">
                              <td>
                                <div className="dash-stock">
                                  <span className="wk-logo">
                                    <StockLogo symbol={s.symbol} />
                                  </span>
                                  <span className="dash-stock-text">
                                    <span className="dash-stock-sym">
                                      {s.symbol}
                                      <InstrumentBadge type={s.instrument_type} />
                                    </span>
                                    {sector && <span className="dash-stock-sub">{sector}</span>}
                                  </span>
                                </div>
                              </td>
                              {isDivergenceTab && (
                                <td>
                                  {tfs.length > 0 ? (
                                    <span className="timeframe-chip">{tfs.map((t) => TF_LABEL[t] ?? t).join(" + ")}</span>
                                  ) : (
                                    "—"
                                  )}
                                </td>
                              )}
                              {isAbTab && (
                                <>
                                  <td>
                                    {detail ? (
                                      <span className="dash-two">
                                        {fmtDate(detail.a_date)}
                                        <small>{fmtPrice(detail.a_price)}</small>
                                      </span>
                                    ) : (
                                      "—"
                                    )}
                                  </td>
                                  <td>
                                    {detail ? (
                                      <span className="dash-two">
                                        {fmtDate(detail.b_date)}
                                        <small>{fmtPrice(detail.b_price)}</small>
                                      </span>
                                    ) : (
                                      "—"
                                    )}
                                  </td>
                                </>
                              )}
                              <td>{fmtDate(s.signal_date)}</td>
                              {isDivergenceTab ? (
                                <>
                                  <td className="num-cell">{fmt(leg?.rsi1 ?? null)}</td>
                                  <td className="num-cell">{fmt(leg?.rsi2 ?? null)}</td>
                                  <td>
                                    {isFormingTab && detail?.distance != null ? (
                                      <span className="muted">{detail.distance} candles</span>
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
                              <td className="num-cell">{fmtPrice(price)}</td>
                              <td className="dash-chart-cell">
                                <button
                                  type="button"
                                  className="wk-chart-btn"
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
                                  aria-label={`Open the ${s.symbol} chart`}
                                >
                                  <TrendIcon width={13} height={13} aria-hidden="true" />
                                  Chart
                                </button>
                              </td>
                            </tr>
                          );
                        })
                      )}
                    </tbody>
                  </table>
                </div>
                {!scanning && filtered.length > 0 && (
                  <div className="dash-pagination">
                    <span>
                      {totalPages > 1
                        ? `Showing ${(currentPage - 1) * PAGE_SIZE + 1}–${Math.min(currentPage * PAGE_SIZE, filtered.length)} of ${filtered.length} signals`
                        : `${filtered.length} signal${filtered.length === 1 ? "" : "s"}`}
                    </span>
                    {totalPages > 1 && (
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
                    )}
                  </div>
                )}
              </>
            )}
          </section>
        </>
      )}

      {selected && (
        <StockDetailPanel signal={selected} richData={richBySymbol.get(selected.symbol) ?? null} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
