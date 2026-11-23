import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { angleColor, angleName, getGannStock, searchGannStocks, type GannStockDetail } from "../services/gannTimeApi";
import { StockLogo } from "../components/StockLogo";
import { GannChart } from "./gannTime/GannChart";
import { AngleFanMotif, PageHero } from "../components/PageHero";
import "./gannTime/gannTime.css";

/**
 * Angle Projection (2026-11-23): the Gann angle-halving fan from the last big swing, for any NSE stock or MCX
 * commodity. Same data as Gann Square (/api/gann-time/stock), shown as candles + swings + angle lines only.
 * A picture, not a signal: on gold 2010-2026 price turned at these lines no more often than at random lines.
 */

const SAVED_KEY = "gann-angles:stock";
const loadSaved = (): GannStockDetail | null => {
  try {
    const raw = localStorage.getItem(SAVED_KEY);
    return raw ? (JSON.parse(raw) as GannStockDetail) : null;
  } catch {
    return null;
  }
};
const fmtDate = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
const fmtPrice = (v: number) => `₹${v.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export function GannAnglesPage() {
  const [params, setParams] = useSearchParams();
  const symbol = (params.get("symbol") ?? loadSaved()?.symbol ?? "").toUpperCase();
  const [query, setQuery] = useState(symbol);
  const [hits, setHits] = useState<{ symbol: string; company_name: string }[]>([]);
  const [data, setData] = useState<GannStockDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runId, setRunId] = useState(0);
  const pick = (s: string) => setParams({ symbol: s });

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
    const saved = loadSaved();
    if (runId === 0 && saved && saved.symbol === symbol) { setData(saved); return; } // last result, from this device
    setLoading(true);
    setError(null);
    getGannStock(symbol)
      .then((d) => {
        setData(d);
        try { localStorage.setItem(SAVED_KEY, JSON.stringify(d)); } catch { /* storage full: still on screen */ }
      })
      .catch((e) => { setData(null); setError(e instanceof Error ? e.message : "No data for this symbol."); })
      .finally(() => setLoading(false));
  }, [symbol, runId]);

  const run = () => {
    const q = query.trim().toUpperCase();
    if (!q) return;
    const s = hits.find((h) => h.symbol === q)?.symbol ?? hits[0]?.symbol ?? q;
    if (s === symbol) setRunId((n) => n + 1);
    else pick(s);
  };

  const fan = data?.angles ?? null;
  const dark = document.documentElement.getAttribute("data-theme") === "dark"
    || (!document.documentElement.hasAttribute("data-theme") && window.matchMedia("(prefers-color-scheme: dark)").matches);
  const lines = fan ? [...fan.lines].sort((a, b) => b.today - a.today) : [];
  const close = data?.last_close ?? 0;
  const above = lines.filter((l) => l.today >= close).at(-1) ?? null; // the lowest line above price
  const below = lines.find((l) => l.today < close) ?? null; // the highest line below price
  const pctFrom = (level: number) => `${level >= close ? "+" : ""}${(((level - close) / close) * 100).toFixed(1)}%`;
  return (
    <div className="page angle-page">
      <PageHero
        tone="angle"
        eyebrow="Gann · price angles"
        title="Angle Projection"
        subtitle="The last big swing's angle, then each half of it, drawn forward from the swing. A picture of where price may meet a line — not a buy or sell signal."
        motif={<AngleFanMotif />}
      >
        <span className="hero-pill">1 candle = 1 ATR scale</span>
        <span className="hero-pill hero-pill-soft">Full · 1/2 · 1/4 · 1/8 … and mirrored</span>
      </PageHero>

      <section className="card gt-search-card">
        <div className="gt-run">
          <div className="gt-search">
            <input
              type="search"
              placeholder="Any NSE stock or commodity — name or symbol (e.g. Reliance, DIVISLAB, Gold, Crude)"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") run(); }}
              aria-label="Search an NSE stock or commodity"
            />
            {hits.length > 0 && (
              <div className="gt-hits">
                {hits.map((h) => (
                  <button type="button" key={h.symbol} onClick={() => pick(h.symbol)}>
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
          <div className="state-title">Pick a stock or commodity</div>
          <div className="state-subtitle">Type a name or symbol and press Run scan to see its Gann angle lines.</div>
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
            </div>
            <GannChart data={data} bands={false} />
            <p className="muted small gt-legend">
              <span className="gt-key gt-key-swing" /> swings · thin lines: angle halving (dashed = the same angles the other way)
            </p>
          </section>

          {fan ? (
            <>
              <section className="card">
                <div className="tb-summary-grid wk-kpis">
                  <div className="tb-summary-tile">
                    <div className="tb-summary-label">SWING</div>
                    <div className="tb-summary-value ga-kpi">{fmtDate(fan.origin_date)}</div>
                    <div className="tb-config-hint" style={{ margin: 0 }}>{fmtPrice(fan.origin_price)} → {fmtPrice(fan.end_price)} ({fmtDate(fan.end_date)})</div>
                  </div>
                  <div className="tb-summary-tile">
                    <div className="tb-summary-label">SWING ANGLE</div>
                    <div className="tb-summary-value">{fan.degrees.toFixed(1)}°</div>
                    <div className="tb-config-hint" style={{ margin: 0 }}>1 candle = 1 ATR ({fmtPrice(fan.atr)})</div>
                  </div>
                  <div className="tb-summary-tile">
                    <div className="tb-summary-label">NEAREST LINE ABOVE</div>
                    <div className="tb-summary-value wk-down">{above ? fmtPrice(above.today) : "—"}</div>
                    <div className="tb-config-hint" style={{ margin: 0 }}>{above ? `${angleName(above.fraction)} · ${pctFrom(above.today)}` : "price is above every line"}</div>
                  </div>
                  <div className="tb-summary-tile">
                    <div className="tb-summary-label">NEAREST LINE BELOW</div>
                    <div className="tb-summary-value wk-up">{below ? fmtPrice(below.today) : "—"}</div>
                    <div className="tb-config-hint" style={{ margin: 0 }}>{below ? `${angleName(below.fraction)} · ${pctFrom(below.today)}` : "price is below every line"}</div>
                  </div>
                </div>
              </section>

              <section className="card">
                <div className="dash-card-head">
                  <div>
                    <h2>Angle lines today</h2>
                    <p className="muted small">
                      Each line&apos;s level on the last candle, highest first. Colours match the chart; the two lines nearest the
                      price are highlighted.
                    </p>
                  </div>
                </div>
                <div className="table-wrap">
                  <table className="dash-signal-table ga-table">
                    <thead>
                      <tr>
                        <th>Line</th>
                        <th className="num-cell">Angle</th>
                        <th className="num-cell">Level today</th>
                        <th className="num-cell">From price</th>
                        <th>Side</th>
                      </tr>
                    </thead>
                    <tbody>
                      {lines.map((l) => (
                        <tr key={l.fraction} className={l === above || l === below ? "ga-near" : ""}>
                          <td>
                            <span className="ga-line">
                              <span className={`ga-swatch${l.fraction < 0 ? " ga-dashed" : ""}`} style={{ borderColor: angleColor(l.fraction, dark) }} />
                              {angleName(l.fraction)}
                            </span>
                          </td>
                          <td className="num-cell">{l.degrees.toFixed(2)}°</td>
                          <td className="num-cell">{fmtPrice(l.today)}</td>
                          <td className={`num-cell ${l.today >= data.last_close ? "wk-down" : "wk-up"}`}>{pctFrom(l.today)}</td>
                          <td className="muted">{l.today >= data.last_close ? "above price" : "below price"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="muted small ga-note">
                  How it is drawn: the last swing of at least 3 ATR ({fmtDate(fan.origin_date)} → {fmtDate(fan.end_date)}) makes{" "}
                  {fan.degrees.toFixed(1)}°; each line halves that angle again, and dashed lines are the same angles the other way.
                  Backtest on gold (2010–2026): price turned at these lines no more often than at random lines — use them as a
                  picture of nearby levels, together with your own setup.
                </p>
              </section>
            </>
          ) : (
            <section className="card">
              <p className="muted dash-empty">No swing of at least 3 ATR in the recent candles, so there is no angle fan to draw.</p>
            </section>
          )}
        </>
      )}
    </div>
  );
}
