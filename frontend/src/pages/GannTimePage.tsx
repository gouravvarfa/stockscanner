import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  getGannSectors,
  getGannStock,
  searchGannStocks,
  startGannSectors,
  type GannCluster,
  type GannSectorScan,
  type GannStockDetail,
} from "../services/gannTimeApi";
import { StockLogo } from "../components/StockLogo";
import { TrendIcon } from "../components/icons";
import { GannChart } from "./gannTime/GannChart";
import "./gannTime/gannTime.css";

/**
 * Gann Time Dates: candle counts between swings projected forward (Gann time cycle). Only "cluster" dates - where two or
 * more projections meet - are shown, for the next 3 months. It says WHEN a turn may come, never which way.
 * 2026-11-22: English, Weekly Sectors layout, and a Run scan button on the single-stock tab.
 */

// Last results stay on this device until a new scan replaces them (2026-11-22): page changes, other scans and
// server restarts never wipe them.
const SECTORS_KEY = "gann:sectors";
const STOCK_KEY = "gann:stock";
function loadSaved<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}
function save(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage full or blocked: the result is still on screen */
  }
}

const fmtDate = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
const fmtPrice = (v: number) => `₹${v.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const fmtPct = (v: number | null) => (v === null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(1)}%`);
const swing = (k: string) => (k === "H" ? "Swing high" : "Swing low");

function whenLabel(barsAway: number): string {
  if (barsAway < 0) return `window open (${-barsAway} ${-barsAway === 1 ? "day" : "days"} ago)`;
  if (barsAway === 0) return "today";
  if (barsAway === 1) return "tomorrow";
  return `in ${barsAway} trading days`;
}

function When({ c }: { c: GannCluster }) {
  return <span className={c.bars_away <= 1 ? "gt-when gt-when-now" : "gt-when"}>{whenLabel(c.bars_away)}</span>;
}

function Strength({ n }: { n: number }) {
  return <span className={`gt-strength gt-strength-${Math.min(n, 4)}`}>{n} projections</span>;
}

/* ------------------------------------------------------------ strong sectors */
function SectorView({ onOpen }: { onOpen: (symbol: string) => void }) {
  const [data, setDataRaw] = useState<GannSectorScan | null>(() => loadSaved<GannSectorScan>(SECTORS_KEY));
  const [error, setError] = useState<string | null>(null);
  // the server's view wins while it is running or has something; an idle server (e.g. after a restart) never
  // hides the result saved on this device; a finished scan replaces the saved one
  const setData = (next: GannSectorScan) => {
    if (next.status === "idle") return;
    if (next.status === "done") save(SECTORS_KEY, next);
    setDataRaw(next);
  };

  async function start() {
    setError(null);
    try {
      setData(await startGannSectors(true));
    } catch (e) {
      setError(e instanceof Error ? e.message : "The scan could not start.");
    }
  }
  // Opening the page only shows the last result (if any); a scan starts only on "Run scan".
  useEffect(() => {
    getGannSectors().then(setData).catch((e) => setError(e instanceof Error ? e.message : "No data."));
  }, []);

  const running = data?.status === "running";
  useEffect(() => {
    if (!running) return;
    const id = window.setInterval(() => {
      getGannSectors().then(setData).catch((e) => setError(e instanceof Error ? e.message : "Refresh failed."));
    }, 2500);
    return () => window.clearInterval(id);
  }, [running]);

  const pct = data && data.total ? Math.round((data.processed / data.total) * 100) : 0;
  const strong = data?.sectors.filter((s) => s.strong) ?? [];

  return (
    <>
      <section className="card">
        <div className="gt-run">
          <button type="button" className="primary-button" onClick={() => void start()} disabled={running}>
            {running ? "Scanning…" : data && data.status !== "idle" ? "Run again" : "Run scan"}
          </button>
          <span className="muted small">
            {running
              ? `Checking A Group stocks… ${data?.processed} / ${data?.total} (${pct}%). The list fills in as it goes.`
              : data?.status === "done" && data.finished_at
                ? `${data.rows.length} stocks · ${strong.length} strong sectors · updated ${new Date(`${data.finished_at}Z`).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "numeric", minute: "2-digit" })}${data.failed > 0 ? ` · ${data.failed} without data` : ""}`
                : "Checks the ~600 A Group stocks and keeps those of today's strong sectors (a few minutes)."}
          </span>
        </div>
        {running && (
          <div className="gt-progress">
            <div style={{ width: `${pct}%` }} />
          </div>
        )}
      </section>

      {(error || data?.status === "error") && <div className="error-banner">{error ?? data?.error}</div>}

      {data && data.status !== "error" && data.status !== "idle" && (
        <section className="card">
          <div className="dash-card-head">
            <div>
              <h2>Next turn dates</h2>
              <p className="muted small">Stocks of the strong sectors with a cluster date in the next 3 months, soonest first.</p>
            </div>
          </div>
          {data.rows.length === 0 ? (
            <p className="muted dash-empty">
              {running ? "Nothing yet — the scan is still running." : "No cluster date in the strong sectors over the next 3 months."}
            </p>
          ) : (
            <div className="table-wrap">
              <table className="dash-signal-table">
                <thead>
                  <tr>
                    <th>Stock</th>
                    <th>Sector</th>
                    <th>Next date</th>
                    <th>Strength</th>
                    <th>Date after</th>
                    <th className="num-cell">Price</th>
                    <th aria-label="Chart" />
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((r) => (
                    <tr key={r.symbol} className="clickable-row" onClick={() => onOpen(r.symbol)}>
                      <td>
                        <div className="dash-stock">
                          <span className="wk-logo"><StockLogo symbol={r.symbol} /></span>
                          <span className="dash-stock-text">
                            <span className="dash-stock-sym">{r.symbol}</span>
                            <span className="dash-stock-sub">
                              {r.company_name}
                              {r.new_swing_forming ? " · new swing forming" : ""}
                            </span>
                          </span>
                        </div>
                      </td>
                      <td className="muted">{r.sector}</td>
                      <td>
                        <span className="dash-two">
                          {fmtDate(r.clusters[0].date)}
                          <small><When c={r.clusters[0]} /></small>
                        </span>
                      </td>
                      <td><Strength n={r.clusters[0].strength} /></td>
                      <td className="muted">{r.clusters[1] ? fmtDate(r.clusters[1].date) : "—"}</td>
                      <td className="num-cell">{fmtPrice(r.close)}</td>
                      <td className="dash-chart-cell">
                        <button
                          type="button"
                          className="wk-chart-btn"
                          onClick={(e) => { e.stopPropagation(); onOpen(r.symbol); }}
                          aria-label={`Open ${r.symbol}`}
                        >
                          <TrendIcon width={13} height={13} aria-hidden="true" />
                          Open
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {data && data.sectors.length > 0 && (
        <section className="card">
          <div className="act-top">
            <h2 style={{ margin: 0 }}>Sector strength</h2>
            <span className="muted small">Nifty 50: 1M {fmtPct(data.nifty_1m)} · 3M {fmtPct(data.nifty_3m)}</span>
          </div>
          <div className="act-grid hm-watch-grid">
            {[
              { tone: "watch", title: "Strong sectors", list: strong, note: "Ahead of the Nifty 50 on the median 1M + 3M return; the top 3 always count. Their stocks are listed above." },
              { tone: "weak", title: "Other sectors", list: data.sectors.filter((s) => !s.strong), note: "Behind the Nifty 50. Sectors with fewer than 3 stocks are left out." },
            ].map((b) => (
              <div key={b.tone} className={`act-box act-${b.tone}`}>
                <div className="act-head">
                  <span className="act-name">{b.title}</span>
                  <span className="act-count">{b.list.length}</span>
                </div>
                <p className="act-note">{b.note}</p>
                {b.list.length === 0 ? <p className="act-empty">None</p> : (
                  <ul className="act-items gt-static">
                    {b.list.map((s) => (
                      <li key={s.sector}>
                        <span className="act-main">{s.sector}</span>
                        <span className="act-sub">{s.stocks} stocks · 1M {fmtPct(s.ret_1m)} · 3M {fmtPct(s.ret_3m)}</span>
                        <span className={s.strong ? "act-val wk-up" : "act-val wk-down"}>{fmtPct(s.score)}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        </section>
      )}
    </>
  );
}

/* ------------------------------------------------------------ single stock */
function StockView({ symbol, onPick }: { symbol: string; onPick: (s: string) => void }) {
  const [query, setQuery] = useState(symbol);
  const [hits, setHits] = useState<{ symbol: string; company_name: string }[]>([]);
  const [data, setData] = useState<GannStockDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runId, setRunId] = useState(0);

  useEffect(() => {
    const q = query.trim();
    if (!q || q.toUpperCase() === symbol) { setHits([]); return; }
    const id = window.setTimeout(() => { searchGannStocks(q).then(setHits).catch(() => setHits([])); }, 200);
    return () => window.clearTimeout(id);
  }, [query, symbol]);

  useEffect(() => {
    if (!symbol) return;
    setQuery(symbol);
    setHits([]);
    const saved = loadSaved<GannStockDetail>(STOCK_KEY);
    if (runId === 0 && saved && saved.symbol === symbol) {
      setData(saved); // the last analysis, straight from this device; Run scan refreshes it
      return;
    }
    setLoading(true);
    setError(null);
    getGannStock(symbol)
      .then((d) => {
        setData(d);
        save(STOCK_KEY, d);
      })
      .catch((e) => { setData(null); setError(e instanceof Error ? e.message : "No data for this stock."); })
      .finally(() => setLoading(false));
  }, [symbol, runId]);

  // Run scan: the picked stock, else the first match, else exactly what was typed.
  const run = () => {
    const q = query.trim().toUpperCase();
    if (!q) return;
    const pick = hits.find((h) => h.symbol === q)?.symbol ?? hits[0]?.symbol ?? q;
    if (pick === symbol) setRunId((n) => n + 1);
    else onPick(pick);
  };

  const projections = useMemo(() => (data?.projections ?? []).slice().sort((a, b) => a.bars_away - b.bars_away), [data]);

  return (
    <>
      <section className="card gt-search-card">
        <div className="gt-run">
          <div className="gt-search">
            <input
              type="search"
              placeholder="Any NSE stock — name or symbol (e.g. Reliance, DIVISLAB)"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") run(); }}
              aria-label="Search an NSE stock"
            />
            {hits.length > 0 && (
              <div className="gt-hits">
                {hits.map((h) => (
                  <button type="button" key={h.symbol} onClick={() => onPick(h.symbol)}>
                    <span className="wk-logo"><StockLogo symbol={h.symbol} /></span>
                    <span className="dash-stock-sym">{h.symbol}</span>
                    <span className="muted small">{h.company_name}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          <button type="button" className="primary-button" onClick={run} disabled={loading || !query.trim()}>
            {loading ? "Scanning…" : "Run scan"}
          </button>
        </div>
      </section>

      {error && <div className="error-banner">{error}</div>}
      {!symbol && !loading && (
        <div className="card state-block">
          <div className="state-title">Pick a stock</div>
          <div className="state-subtitle">Type a name or symbol and press Run scan to see its next Gann turn dates.</div>
        </div>
      )}

      {data && (
        <>
          <section className="card">
            <div className="dash-card-head">
              <div className="dash-stock">
                <span className="wk-logo"><StockLogo symbol={data.symbol} /></span>
                <div>
                  <h2>{data.company_name}</h2>
                  <p className="muted small">
                    {data.symbol}{data.sector ? ` · ${data.sector}` : ""} · last candle {fmtDate(data.last_date)} · {fmtPrice(data.last_close)}
                  </p>
                </div>
              </div>
              {data.new_swing_forming && <span className="gt-warn">A new swing is forming — dates may shift</span>}
            </div>
            <GannChart data={data} />
            <p className="muted small gt-legend">
              <span className="gt-key gt-key-swing" /> swings
              <span className="gt-key gt-key-band" /> cluster date
              <span className="gt-key gt-key-soft" /> ±3 candle window
            </p>
          </section>

          <section className="card">
            <div className={`act-box act-${data.clusters.length ? "watch" : "weak"}`}>
              <div className="act-head">
                <span className="act-name">Cluster dates · next 3 months</span>
                <span className="act-count">{data.clusters.length}</span>
              </div>
              <p className="act-note">
                Where two or more projections land within ±2 candles. A turn can come anywhere in the ±3 candle window — act only
                when price or RSI confirms it.
              </p>
              {data.clusters.length === 0 ? (
                <p className="act-empty">No cluster in the next 3 months; single dates are not shown.</p>
              ) : (
                <ul className="act-items gt-static">
                  {data.clusters.map((c) => (
                    <li key={c.date}>
                      <span className="act-main">{fmtDate(c.date)} · <When c={c} /></span>
                      <span className="act-sub">{c.projections.map((p) => `${p.label} of ${p.count} candles`).join(" · ")}</span>
                      <span className="act-val"><Strength n={c.strength} /></span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>

          <div className="gt-grid">
            <section className="card">
              <div className="dash-card-head">
                <div>
                  <h2>Candle counts</h2>
                  <p className="muted small">Candles between the recent swings</p>
                </div>
              </div>
              <div className="table-wrap">
                <table className="dash-signal-table">
                  <thead><tr><th>From</th><th>To</th><th className="num-cell">Candles</th></tr></thead>
                  <tbody>
                    {data.counts.map((c) => (
                      <tr key={c.from_date}>
                        <td><span className="dash-two">{fmtDate(c.from_date)}<small>{swing(c.from_kind)}</small></span></td>
                        <td><span className="dash-two">{fmtDate(c.to_date)}<small>{swing(c.to_kind)}</small></span></td>
                        <td className="num-cell">{c.candles}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
            <section className="card">
              <div className="dash-card-head">
                <div>
                  <h2>All projections</h2>
                  <p className="muted small">Every projected date in the next 3 months</p>
                </div>
              </div>
              {projections.length === 0 ? (
                <p className="muted dash-empty">No projection.</p>
              ) : (
                <ul className="act-items gt-static gt-proj-list">
                  {projections.map((p, i) => (
                    <li key={i}>
                      <span className="act-main">{fmtDate(p.date)}</span>
                      <span className="act-sub">{p.label} of {p.count} candles · from {fmtDate(p.source_date)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        </>
      )}
    </>
  );
}

/* ------------------------------------------------------------ page */
export function GannTimePage() {
  const [params, setParams] = useSearchParams();
  // Single stock first (user, 2026-11-22); the Strong sectors scan is the second tab.
  const tab = params.get("tab") === "sectors" ? "sectors" : "stock";
  const symbol = (params.get("symbol") ?? loadSaved<GannStockDetail>(STOCK_KEY)?.symbol ?? "").toUpperCase();
  const openStock = (s: string) => setParams({ tab: "stock", symbol: s });

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Gann Time Dates</h1>
          <p className="page-subtitle">
            Candle counts between swings, projected forward (Gann time cycle). Only cluster dates for the next 3 months are
            shown. It tells you when a turn may come, not which way.
          </p>
        </div>
      </div>

      <div className="tabs gt-tabs" role="tablist" aria-label="View">
        <button type="button" role="tab" aria-selected={tab === "stock"} className={tab === "stock" ? "tab active" : "tab"} onClick={() => setParams(symbol ? { tab: "stock", symbol } : { tab: "stock" })}>
          Single stock
        </button>
        <button type="button" role="tab" aria-selected={tab === "sectors"} className={tab === "sectors" ? "tab active" : "tab"} onClick={() => setParams({ tab: "sectors" })}>
          Strong sectors
        </button>
      </div>

      {tab === "sectors" ? <SectorView onOpen={openStock} /> : <StockView symbol={symbol} onPick={openStock} />}
    </div>
  );
}
