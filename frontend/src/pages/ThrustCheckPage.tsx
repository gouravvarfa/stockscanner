import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { PageHero } from "../components/PageHero";
import { StockLogo } from "../components/StockLogo";
import { searchGannStocks } from "../services/gannTimeApi";
import { getThrust, type ThrustCheck } from "../services/thrustApi";
import "./gannTime/gannTime.css";

/**
 * Thrust Check (2026-11-23): for one stock or commodity, is the move from its last confirmed swing "stretched"
 * (1 ATR or more per candle)? Tested on 613 series 2005-2026: after such a thrust a new swing formed within ±3 days
 * 42-53% of the time against 33% at random and price came back 1 ATR 80-86% of the time, but trading against it
 * averaged about 0R. So it is a warning — do not chase — never an entry.
 */

const SAVED_KEY = "thrust:stock";
const loadSaved = (): ThrustCheck | null => {
  try { const raw = localStorage.getItem(SAVED_KEY); return raw ? (JSON.parse(raw) as ThrustCheck) : null; } catch { return null; }
};
const fmtDate = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
const num = (v: number) => v.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function ThrustMotif() {
  return (
    <svg viewBox="-110 -80 220 160" className="motif-svg">
      <line x1={-90} y1={55} x2={90} y2={-65} className="m-faint" />
      <path d="M -90 55 L -60 48 L -40 52 L -20 30 L 0 6 L 18 -22 L 34 -48 L 46 -30 L 58 -36" className="m-pulse" />
      <circle cx={34} cy={-48} r={6} className="m-mark" />
      <text x={0} y={70} className="m-lab" textAnchor="middle">1 ATR per candle</text>
    </svg>
  );
}

const STATUS: Record<ThrustCheck["status"], { label: string; cls: string; text: string }> = {
  stretched: { label: "Stretched — don't chase", cls: "th-hot", text: "A thrust fired in the last 3 candles. A pullback of about 1 ATR usually comes within 1–2 days; a fresh entry here is late." },
  fired: { label: "Thrust fired earlier", cls: "th-warm", text: "This swing already had a thrust; it is more than 3 candles old now." },
  normal: { label: "Normal pace", cls: "th-calm", text: "The move from the last swing is below 1 ATR per candle — no thrust." },
};

export function ThrustCheckPage() {
  const [params, setParams] = useSearchParams();
  const symbol = (params.get("symbol") ?? loadSaved()?.symbol ?? "").toUpperCase();
  const [query, setQuery] = useState(symbol);
  const [hits, setHits] = useState<{ symbol: string; company_name: string }[]>([]);
  const [data, setData] = useState<ThrustCheck | null>(null);
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
    setQuery(symbol); setHits([]);
    const saved = loadSaved();
    if (runId === 0 && saved && saved.symbol === symbol) { setData(saved); return; }
    setLoading(true); setError(null);
    getThrust(symbol)
      .then((d) => { setData(d); try { localStorage.setItem(SAVED_KEY, JSON.stringify(d)); } catch { /* full */ } })
      .catch((e) => { setData(null); setError(e instanceof Error ? e.message : "No data for this symbol."); })
      .finally(() => setLoading(false));
  }, [symbol, runId]);

  const run = () => {
    const q = query.trim().toUpperCase();
    if (!q) return;
    const s = hits.find((h) => h.symbol === q)?.symbol ?? hits[0]?.symbol ?? q;
    if (s === symbol) setRunId((n) => n + 1); else pick(s);
  };

  const st = data ? STATUS[data.status] : null;
  const fill = data ? Math.min(100, (data.pace / 1.5) * 100) : 0;
  return (
    <div className="page thrust-page">
      <PageHero
        tone="outlook"
        eyebrow="Single stock · move speed"
        title="Thrust Check"
        subtitle="Has the move from the last swing run at 1 ATR or more per candle? Such thrusts often pause or pull back soon — a warning not to chase, never a signal to trade against."
        motif={<ThrustMotif />}
      >
        <span className="hero-pill">Tested on 613 stocks & markets, 2005–2026</span>
        <span className="hero-pill hero-pill-soft">Warning only — not an entry</span>
      </PageHero>

      <section className="card gt-search-card">
        <div className="gt-run">
          <div className="gt-search">
            <input
              type="search"
              placeholder="Any NSE stock or commodity — name or symbol (e.g. Reliance, DIVISLAB, Gold)"
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
            {loading ? "Checking…" : "Run check"}
          </button>
        </div>
      </section>

      {error && <div className="error-banner">{error}</div>}
      {!symbol && !loading && (
        <div className="card state-block">
          <div className="state-title">Pick a stock or commodity</div>
          <div className="state-subtitle">Type a name or symbol and press Run check.</div>
        </div>
      )}

      {data && st && (
        <>
          <section className="card">
            <div className="dash-card-head">
              <div className="dash-stock">
                <span className="wk-logo"><StockLogo symbol={data.symbol} /></span>
                <div>
                  <div className="dash-stock-sym">{data.symbol}</div>
                  <div className="muted small">{data.company_name} · ₹{num(data.last_close)} on {fmtDate(data.last_date)}</div>
                </div>
              </div>
              <span className={`th-status ${st.cls}`}>{st.label}</span>
            </div>
            <p className="th-text">{st.text}</p>

            <div className="th-meter" aria-label={`Pace ${data.pace} ATR per candle`}>
              <div className="th-track"><span style={{ width: `${fill}%` }} className={st.cls} /><i style={{ left: `${(1 / 1.5) * 100}%` }} /></div>
              <div className="th-meter-labels"><span>0</span><b>1 ATR / candle</b><span>1.5</span></div>
            </div>

            <div className="tb-summary-grid wk-kpis">
              <div className="tb-summary-tile">
                <div className="tb-summary-label">LAST SWING</div>
                <div className="tb-summary-value">{data.pivot.kind === "low" ? "Low" : "High"} ₹{num(data.pivot.price)}</div>
                <div className="tb-config-hint" style={{ margin: 0 }}>{fmtDate(data.pivot.date)} · {data.bars_since} candles ago</div>
              </div>
              <div className="tb-summary-tile">
                <div className="tb-summary-label">MOVE SINCE ({data.direction.toUpperCase()})</div>
                <div className="tb-summary-value">₹{num(data.move)}</div>
                <div className="tb-config-hint" style={{ margin: 0 }}>ATR at the swing ₹{num(data.atr)}</div>
              </div>
              <div className="tb-summary-tile">
                <div className="tb-summary-label">PACE NOW</div>
                <div className="tb-summary-value">{data.pace.toFixed(2)} ATR / candle</div>
                <div className="tb-config-hint" style={{ margin: 0 }}>A thrust needs 1.00 (from the 5th candle)</div>
              </div>
              <div className="tb-summary-tile">
                <div className="tb-summary-label">THRUST</div>
                <div className="tb-summary-value">{data.thrust ? fmtDate(data.thrust.date) : "None yet"}</div>
                <div className="tb-config-hint" style={{ margin: 0 }}>
                  {data.thrust ? `${data.thrust.bars_ago} candles ago · pace ${data.thrust.pace}${data.thrust.climax ? " · volume climax" : ""}` : "on this swing"}
                </div>
              </div>
            </div>
          </section>

          <section className="card">
            <div className="dash-card-head">
              <div>
                <h2>{data.symbol}: past thrusts</h2>
                <p className="muted small">
                  On this chart: a new swing formed within ±3 candles after {data.own_record.turned} of {data.own_record.thrusts} thrusts.
                </p>
              </div>
            </div>
            {data.history.length === 0 ? (
              <p className="muted dash-empty">No thrust in the loaded history.</p>
            ) : (
              <div className="table-wrap">
                <table className="dash-signal-table">
                  <thead>
                    <tr><th>Thrust</th><th>Direction</th><th className="num-cell">Candles</th><th className="num-cell">Pace</th><th className="num-cell">Came back</th><th>New swing ±3</th></tr>
                  </thead>
                  <tbody>
                    {data.history.map((h) => (
                      <tr key={h.date + h.from_date}>
                        <td><span className="dash-two">{fmtDate(h.date)}<small>from {fmtDate(h.from_date)}</small></span></td>
                        <td><span className={h.direction === "up" ? "wk-up" : "wk-down"}>{h.direction}</span>{h.climax && <span className="th-climax">climax</span>}</td>
                        <td className="num-cell">{h.bars}</td>
                        <td className="num-cell">{h.pace.toFixed(2)}</td>
                        <td className="num-cell">{h.back_atr == null ? "—" : `${h.back_atr.toFixed(1)} ATR`}</td>
                        <td>{h.turned == null ? <span className="muted small">too recent</span> : h.turned ? "Yes" : "No"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="muted small aw-honest">
              Tested on 613 stocks, indices and commodities (2005–2026), with only confirmed swings: after a thrust a new swing
              formed within ±3 days {data.record.turn_within_3} of the time against {data.record.turn_random} at random, and price came
              back 1 ATR {data.record.back_1atr} of the time, usually in 1–2 days. Trading against the thrust (stop beyond its extreme,
              1R or 2R target) averaged {data.record.avg_r} — so read it as "don&apos;t chase", not as a short or buy signal.
            </p>
          </section>
        </>
      )}

      <p className="muted small aw-foot">
        Daily candles from Angel One. Swing = highest high or lowest low of ±10 candles, counted once 10 candles have closed after it.
        ATR = 14-day average true range at the swing. Volume climax = a candle of 1.5 ATR or more on 1.5× the 20-day volume. For
        education only; not investment advice.
      </p>
    </div>
  );
}
