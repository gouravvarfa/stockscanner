import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  getGannStock,
  searchGannStocks,
  type GannCluster,
  type GannStockDetail,
} from "../services/gannTimeApi";
import { StockLogo } from "../components/StockLogo";
import { GannChart } from "./gannTime/GannChart";
import { PageHero, SquareOfNine } from "../components/PageHero";
import "./gannTime/gannTime.css";

/**
 * Gann Time Dates: candle counts between swings projected forward (Gann time cycle). Only "cluster" dates - where two or
 * more projections meet - are shown, for the next 3 months. It says WHEN a turn may come, never which way.
 * 2026-11-22: English, Weekly Sectors layout, Run scan; any NSE stock or MCX commodity (the sectors scan was removed).
 */

// Last results stay on this device until a new scan replaces them (2026-11-22): page changes, other scans and
// server restarts never wipe them.
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
              placeholder="Any NSE stock or commodity — name or symbol (e.g. Reliance, DIVISLAB, Gold, Crude)"
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
            <GannChart data={data} angles={false} />
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
  const symbol = (params.get("symbol") ?? loadSaved<GannStockDetail>(STOCK_KEY)?.symbol ?? "").toUpperCase();
  const openStock = (s: string) => setParams({ symbol: s });

  return (
    <div className="page gann-page">
      <PageHero
        tone="gann"
        eyebrow="Gann · time cycles"
        title="Gann Square"
        subtitle="Candle counts between swings, projected forward on Gann ratios and the Square of Nine. Only cluster dates for the next 3 months are shown: when a turn may come, not which way."
        motif={<SquareOfNine />}
      >
        <span className="hero-pill">NSE stocks · MCX commodities</span>
        <span className="hero-pill hero-pill-soft">Clusters = 2+ projections within ±2 candles</span>
      </PageHero>

      <StockView symbol={symbol} onPick={openStock} />
    </div>
  );
}
