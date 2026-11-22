import { useMemo, useState } from "react";
import { useChart } from "../chart/ChartContext";
import { ConditionChip } from "../components/ConditionChip";
import { InstrumentBadge } from "../components/InstrumentBadge";
import { TrendIcon, ValueTagIcon } from "../components/icons";
import { useScanJob } from "../hooks/useScanJob";
import type { ScanResult, StrategySignal } from "../services/api";

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
  const { result, partial, job, running, error, cache, run, runFresh, cancel, queued } = useScanJob<ScanResult>("value_buy");
  const { openChart } = useChart();
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("monthly_rsi");
  const [asc, setAsc] = useState(true);

  const signals = useMemo(() => result?.strategies?.["Value Buy"] ?? [], [result]);
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
            The whole A Group: monthly RSI in the 38-45 support zone, the latest weekly candle green and a daily key reversal.
          </p>
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          <button className="primary-button" onClick={() => void run()} disabled={running}>
            {running ? "Scanning…" : "Run Scan"}
          </button>
          {!running && (
            <button className="secondary-button" onClick={() => void runFresh()} title="Ignore the saved result and fetch fresh data">
              Fresh Scan
            </button>
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

      {!result && !running && !error && (
        <div className="card state-block">
          <div className="state-icon">
            <ValueTagIcon width={28} height={28} />
          </div>
          <div className="state-title">No Value Buy scan yet</div>
          <div className="state-subtitle">Run a scan to check every A Group stock with the Value Buy rules.</div>
        </div>
      )}

      {result && (
        <>
          <div className="scan-meta card">
            <div>
              Data as of <strong>{new Date(result.finished_at).toLocaleString()}</strong>
              {cacheAge !== null && (
                <span className="muted small">
                  {" "}
                  · saved result, {Math.floor(cacheAge / 3600)}h {Math.floor((cacheAge % 3600) / 60)}m old
                </span>
              )}
            </div>
            <div>
              Stocks scanned: {result.stocks_scanned} · failed: {result.stocks_failed}
            </div>
            <div>
              Value Buy: <strong>{signals.length}</strong>
            </div>
          </div>

          <div className="card">
            <div className="vb-toolbar">
              <h2 style={{ margin: 0 }}>Value Buy stocks</h2>
              <input
                className="vb-search"
                placeholder="Search a stock…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                aria-label="Search a stock"
              />
            </div>
            {rows.length === 0 ? (
              <p className="muted" style={{ marginBottom: 0 }}>
                {signals.length === 0 ? "No A Group stock qualifies for Value Buy right now." : "No stock matches the search."}
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
                        <tr key={s.symbol}>
                          <td>
                            <strong>{s.symbol}</strong> <InstrumentBadge type={s.instrument_type ?? "EQUITY"} />
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
