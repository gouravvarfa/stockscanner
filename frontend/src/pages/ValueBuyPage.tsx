import { useMemo, useState } from "react";
import { useChart } from "../chart/ChartContext";
import { ConditionChip } from "../components/ConditionChip";
import { InstrumentBadge } from "../components/InstrumentBadge";
import { TrendIcon, ValueTagIcon } from "../components/icons";
import { useScanJob } from "../hooks/useScanJob";
import { newerOf, useEodResult } from "../hooks/useEodResult";
import type { ScanResult, StrategySignal } from "../services/api";
import { StockLogo } from "../components/StockLogo";
import { SupportZoneCard, inMode, type SupportRow, type VbMode } from "./valueBuy/SupportZoneCard";

/** The Value Buy result also carries today's STRONG sectors and their stocks (2026-11-23). */
type ValueBuyResult = ScanResult & {
  strong_sectors?: { key: string; label: string }[];
  strong_symbols?: Record<string, string>;
  support_zone?: SupportRow[];
  sector_status?: { key: string; label: string; rsi: { d: number | null; w: number | null; m: number | null }; status: "strong" | "value" | null }[];
};
const STRONG_KEY = "value-buy:strong-only";

/**
 * Value Buy on its own page (2026-11-22): the whole A Group, checked with the Value Buy rules only (monthly RSI in the
 * 38-45 support zone, the latest weekly candle green, a daily key reversal). The Dashboard covers only the STRONG
 * sectors, so Value Buy lives here, with its own background scan job ("value_buy").
 */

const CONDITION_LABELS: Record<string, string> = {
  monthly_rsi_in_support_zone: "Monthly RSI 38-45",
  latest_confirmed_weekly_candle_green: "Weekly candle green",
  daily_key_reversal: "Daily key reversal",
};

type SortKey = "symbol" | "price" | "daily_rsi" | "weekly_rsi" | "monthly_rsi";

function fmt(v: number | null | undefined, digits = 1): string {
  return v === null || v === undefined || Number.isNaN(v) ? "—" : v.toFixed(digits);
}

function priceOf(s: StrategySignal): number | null {
  const p = s.extra.current_price;
  return typeof p === "number" ? p : null;
}

function minutes(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "estimating…";
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

export function ValueBuyPage() {
  const { result, partial, job, running, error, cache, run, runFresh, cancel, queued } = useScanJob<ValueBuyResult>("value_buy");
  const eodVb = useEodResult<ValueBuyResult>("value_buy");
  const { shown: vb, isEod } = newerOf(running ? null : result, eodVb);
  const [strongOnly, setStrongOnly] = useState<boolean>(() => {
    try { return localStorage.getItem(STRONG_KEY) !== "0"; } catch { return true; }
  });
  const toggleStrong = (on: boolean) => {
    setStrongOnly(on);
    try { localStorage.setItem(STRONG_KEY, on ? "1" : "0"); } catch { /* not saved */ }
  };
  const strongMap = useMemo(() => vb?.strong_symbols ?? {}, [vb]);
  // only when the result really carries strong sectors (the NSE end-of-day result may not): otherwise show every stock
  const hasStrongInfo = !!vb?.strong_symbols && Object.keys(vb.strong_symbols).length > 0;
  const { openChart } = useChart();
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("monthly_rsi");
  const [asc, setAsc] = useState(true);
  const [view, setView] = useState<VbMode | "vb">("all");

  const allSignals = useMemo(() => vb?.strategies?.["Value Buy"] ?? [], [vb]);
  const strongCount = useMemo(() => allSignals.filter((s) => strongMap[s.symbol]).length, [allSignals, strongMap]);
  const signals = useMemo(
    () => (strongOnly && hasStrongInfo ? allSignals.filter((s) => strongMap[s.symbol]) : allSignals),
    [allSignals, strongOnly, hasStrongInfo, strongMap],
  );
  const rows = useMemo(() => {
    const q = query.trim().toUpperCase();
    const list = q ? signals.filter((s) => s.symbol.toUpperCase().includes(q)) : [...signals];
    const value = (s: StrategySignal): number | string =>
      sortKey === "symbol" ? s.symbol : sortKey === "price" ? priceOf(s) ?? -Infinity : s[sortKey] ?? -Infinity;
    list.sort((a, b) => {
      const av = value(a);
      const bv = value(b);
      const d = typeof av === "string" ? av.localeCompare(String(bv)) : (av as number) - (bv as number);
      return asc ? d : -d;
    });
    return list;
  }, [signals, query, sortKey, asc]);

  const sortBy = (key: SortKey) => {
    if (key === sortKey) setAsc(!asc);
    else {
      setSortKey(key);
      setAsc(true);
    }
  };
  const arrow = (key: SortKey) => (key === sortKey ? (asc ? " ▲" : " ▼") : "");

  const showChart = (s: StrategySignal) =>
    openChart(s.symbol, {
      strategy: "Value Buy",
      daily_rsi: s.daily_rsi,
      weekly_rsi: s.weekly_rsi,
      monthly_rsi: s.monthly_rsi,
      signal_date: s.signal_date,
      explanation: s.explanation,
      indicators: { rsi: true, volume: true, bollinger: true },
    });

  const liveFound = partial.filter((p) => p.strategies.includes("Value Buy"));
  const cacheAge = cache ? (Date.now() - new Date(cache.completed_at).getTime()) / 1000 : null;

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Value Buy</h1>
          <p className="page-subtitle">
            Stocks at the monthly RSI 40 support (38–45, this month&apos;s candle, green) from your sectors that are Strong or themselves at the 40 support, with 3–5 drives. The 78% pullback and ★ Best are tags.
          </p>
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          {eodVb && !running ? (
            <>
              <span className="eod-ready">✓ Ready · NSE data of {new Date(`${eodVb.data_as_of}T00:00:00`).toLocaleDateString("en-IN", { day: "2-digit", month: "short" })} · no scan needed</span>
            </>
          ) : (
            <>
              <button className="primary-button" onClick={() => void run()} disabled={running}>
                {running ? "Scanning…" : "Run Scan"}
              </button>
              {!running && (
                <button className="secondary-button" onClick={() => void runFresh()} title="Ignore the saved result and fetch fresh data">
                  Fresh Scan
                </button>
              )}
            </>
          )}
          {running && (
            <button className="secondary-button stop-scan-button" onClick={() => void cancel()}>
              Stop Scan
            </button>
          )}
        </div>
      </div>

      {running && job && (
        <div className="card scan-meta" style={{ marginBottom: 12 }}>
          <div style={{ width: "100%" }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 6 }}>
              <span>Scanning{job.current_symbol ? `: ${job.current_symbol}` : "…"}</span>
              <span>
                {job.processed} / {job.total || "?"} ({job.percentage.toFixed(1)}%)
              </span>
            </div>
            <div className="active-scan-bar">
              <div className="active-scan-bar-fill" style={{ transform: `scaleX(${Math.min(job.percentage, 100) / 100})` }} />
            </div>
            <div style={{ fontSize: 12, opacity: 0.7, marginTop: 6 }}>
              Value Buy found {liveFound.length} · Failed {job.failed} · Elapsed {minutes(job.elapsed_seconds)} · ETA {minutes(job.eta_seconds)}
            </div>
            {liveFound.length > 0 && (
              <div className="live-results">
                {liveFound.slice(-40).map((p) => (
                  <span key={p.seq} className="live-result-chip">
                    {p.symbol}
                    <InstrumentBadge type={p.instrument_type} />
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {queued && (
        <div className="notice-banner queue-banner">
          <span>{queued}</span>
          <button type="button" className="secondary-button" onClick={() => void cancel()}>Cancel</button>
        </div>
      )}
      {error && <div className={running ? "notice-banner" : "error-banner"}>{error}</div>}

      {!vb && !running && !error && (
        <div className="card state-block">
          <div className="state-icon">
            <ValueTagIcon width={28} height={28} />
          </div>
          <div className="state-title">No Value Buy scan yet</div>
          <div className="state-subtitle">Run a scan to check every NSE stock with the Value Buy rules.</div>
        </div>
      )}

      {vb && (
        <>
          <div className="scan-meta card">
            <div>
              {isEod ? (
                <>NSE end-of-day data as of <strong>{new Date(`${(vb as ValueBuyResult & { data_as_of: string }).data_as_of}T00:00:00`).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" })}</strong>
                  <span className="muted small"> · every NSE stock, updated each evening — no scan needed</span></>
              ) : (
                <>Data as of <strong>{new Date(vb.finished_at).toLocaleString()}</strong></>
              )}
              {!isEod && cacheAge !== null && (
                <span className="muted small">
                  {" "}
                  · saved result, {Math.floor(cacheAge / 3600)}h {Math.floor((cacheAge % 3600) / 60)}m old
                </span>
              )}
            </div>
            <div>
              Stocks scanned: {vb.stocks_scanned} · failed: {vb.stocks_failed}
            </div>
            <div>
              Value Buy: <strong>{vb.support_zone ? vb.support_zone.length : allSignals.length}</strong>
              {hasStrongInfo && <span className="muted small"> · {strongCount} in strong sectors</span>}
            </div>
            {vb.strong_sectors && vb.strong_sectors.length > 0 && (
              <div className="muted small">
                Strong sectors today: {vb.strong_sectors.length ? vb.strong_sectors.map((x) => x.label).join(", ") : "none"}
              </div>
            )}
          </div>

          {vb.sector_status && vb.sector_status.length > 0 && (
            <section className="card vbs-panel">
              <div className="dash-card-head">
                <div>
                  <h2>Your sectors today</h2>
                  <p className="muted small">Value Buy takes stocks only from sectors that are Strong (daily, weekly and monthly RSI above 60) or themselves at the monthly 40 support.</p>
                </div>
              </div>
              <div className="vbs-groups">
                {(["strong", "value"] as const).map((st) => {
                  const list = vb.sector_status!.filter((x) => x.status === st);
                  return (
                    <div key={st} className={`vbs-group vbs-${st}`}>
                      <div className="vbs-group-head">
                        <span className="vbs-dot" />
                        <b>{st === "strong" ? "Strong sectors" : "Sectors at the 40 support"}</b>
                        <span className="vbs-count">{list.length}</span>
                      </div>
                      {list.length === 0 ? (
                        <p className="muted small vbs-empty">{st === "strong" ? "No sector is strong today." : "No sector is at its monthly 40 support today."}</p>
                      ) : (
                        <div className="vbs-cards">
                          {list.map((x) => (
                            <div key={x.key} className="vbs-card">
                              <span className="vbs-name">{x.label}</span>
                              <span className="vbs-rsi">
                                {(["d", "w", "m"] as const).map((k) => (
                                  <span key={k}><small>{k.toUpperCase()}</small>{x.rsi[k] ?? "—"}</span>
                                ))}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </section>
          )}

          <div className="card">
            <div className="vb-toolbar">
              {vb.support_zone ? (
                <div className="vb-seg vb-view" role="tablist" aria-label="List">
                  {([["all", "All"], ["drives", "3–5 Drive"], ["strong", "Strong sector"], ["value", "Sector at 40"]] as const).map(([k, label]) => (
                    <button key={k} type="button" role="tab" aria-selected={view === k} className={view === k ? "active" : ""} onClick={() => setView(k)}>
                      {label} <b>{vb.support_zone!.filter((r) => inMode(r, k)).length}</b>
                    </button>
                  ))}
                </div>
              ) : (
                <h2 style={{ margin: 0 }}>Value Buy stocks</h2>
              )}
              {hasStrongInfo && (
                <div className="vb-seg" role="tablist" aria-label="Which stocks">
                  <button type="button" role="tab" aria-selected={strongOnly} className={strongOnly ? "active" : ""} onClick={() => toggleStrong(true)}>
                    Strong sectors <b>{strongCount}</b>
                  </button>
                  <button type="button" role="tab" aria-selected={!strongOnly} className={!strongOnly ? "active" : ""} onClick={() => toggleStrong(false)}>
                    All stocks <b>{allSignals.length}</b>
                  </button>
                </div>
              )}
              <input
                className="vb-search"
                placeholder="Search a stock…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                aria-label="Search a stock"
              />
            </div>
            {view !== "vb" && vb.support_zone ? (
              <SupportZoneCard key={view} mode={view} rows={vb.support_zone} strongMap={strongMap} strongOnly={strongOnly && hasStrongInfo} query={query} />
            ) : rows.length === 0 ? (
              <p className="muted" style={{ marginBottom: 0 }}>
                {signals.length === 0
                  ? strongOnly && hasStrongInfo && allSignals.length > 0
                    ? `No strong-sector stock qualifies right now — ${allSignals.length} other stock${allSignals.length > 1 ? "s" : ""} do: switch to All stocks.`
                    : "No stock qualifies for Value Buy right now."
                  : "No stock matches the search."}
              </p>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th className="sortable" onClick={() => sortBy("symbol")}>Stock{arrow("symbol")}</th>
                      <th className="sortable num-cell" onClick={() => sortBy("price")}>Price{arrow("price")}</th>
                      <th className="sortable num-cell" onClick={() => sortBy("daily_rsi")}>Daily RSI{arrow("daily_rsi")}</th>
                      <th className="sortable num-cell" onClick={() => sortBy("weekly_rsi")}>Weekly RSI{arrow("weekly_rsi")}</th>
                      <th className="sortable num-cell" onClick={() => sortBy("monthly_rsi")}>Monthly RSI{arrow("monthly_rsi")}</th>
                      <th>Conditions</th>
                      <th>Signal date</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((s) => {
                      const price = priceOf(s);
                      return (
                        <tr key={s.symbol} className="wk-click" title="Open the chart" onClick={(e) => { if (!(e.target as HTMLElement).closest("button, a, input")) showChart(s); }}>
                          <td>
                            <span className="logo-line">
                              <span className="wk-logo"><StockLogo symbol={s.symbol} /></span>
                              <strong>{s.symbol}</strong> <InstrumentBadge type={s.instrument_type ?? "EQUITY"} />
                              {strongMap[s.symbol] && <span className="vb-sector">{strongMap[s.symbol]}</span>}
                            </span>
                          </td>
                          <td className="num-cell">{price === null ? "—" : `₹${price.toFixed(2)}`}</td>
                          <td className="num-cell">{fmt(s.daily_rsi)}</td>
                          <td className="num-cell">{fmt(s.weekly_rsi)}</td>
                          <td className="num-cell">{fmt(s.monthly_rsi)}</td>
                          <td>
                            <div className="chip-row">
                              {Object.entries(s.conditions).map(([k, v]) => (
                                <ConditionChip key={k} label={CONDITION_LABELS[k] ?? k} passed={v} />
                              ))}
                            </div>
                          </td>
                          <td>{s.signal_date ? String(s.signal_date).slice(0, 10) : "—"}</td>
                          <td>
                            <button
                              type="button"
                              className="wk-chart-btn"
                              onClick={() => showChart(s)}
                              title={`Open the ${s.symbol} chart`}
                              aria-label={`Open the ${s.symbol} chart`}
                            >
                              <TrendIcon width={13} height={13} aria-hidden="true" />
                              Chart
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
