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
  stretched: { label: "Stretched — don't chase", cls: "th-hot", text: "It has run too fast in the last few days. Don't buy (or sell) late here — a dip of about one normal day's range usually comes within 1–2 days." },
  fired: { label: "Was stretched earlier", cls: "th-warm", text: "It ran too fast earlier in this move, but that was more than 3 days ago — the warning has passed." },
  normal: { label: "Normal speed", cls: "th-calm", text: "It is moving at a normal speed — nothing stretched, no warning." },
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
        subtitle="Is this stock running too fast? If it has moved a full normal day's range every single day since its last turn, it is stretched — it often pauses or dips soon. A warning not to chase, never a buy or sell signal."
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

      <section className="card th-how">
        <h2>How it works — in 3 steps</h2>
        <ol>
          <li><b>Find the last turn.</b> The latest clear top or bottom (the highest or lowest point of 10 days on each side).</li>
          <li><b>Measure the speed.</b> How far price has moved since then, per day, compared with a normal day&apos;s range for that stock (ATR).</li>
          <li><b>Warn when it is too fast.</b> If it has moved a full normal day&apos;s range or more every day, it is <b>stretched</b>. After that it often pauses or dips, so don&apos;t chase it.</li>
        </ol>
        <p className="muted small">
          Example: a stock that normally moves ₹20 a day and has risen ₹200 in 8 days (₹25 a day = 125%) is stretched. The same ₹200 in 30 days (₹7 a day = 33%) is normal.
        </p>
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
            <div className="th-plain">
              Since its last {data.pivot.kind === "low" ? "bottom" : "top"} on {fmtDate(data.pivot.date)} ({data.bars_since} trading days ago) it has moved{" "}
              <b>{data.direction === "up" ? "up" : "down"} ₹{num(data.move)}</b>. A normal day&apos;s move for it is about <b>₹{num(data.atr)}</b>, so it has
              moved <b>₹{num(data.bars_since > 0 ? data.move / data.bars_since : 0)} a day</b> — <b>{Math.round(data.pace * 100)}%</b> of a normal day&apos;s range
              every day. It is &quot;stretched&quot; only at 100% or more.
            </div>

            <div className="th-meter" aria-label={`Speed ${Math.round(data.pace * 100)}% of a normal day per day`}>
              <div className="th-track"><span style={{ width: `${fill}%` }} className={st.cls} /><i style={{ left: `${(1 / 1.5) * 100}%` }} /></div>
              <div className="th-meter-labels"><span>Slow</span><b>Stretched line (100%)</b><span>Very fast</span></div>
            </div>

            <div className="tb-summary-grid wk-kpis">
              <div className="tb-summary-tile">
                <div className="tb-summary-label">LAST TURN</div>
                <div className="tb-summary-value">{data.pivot.kind === "low" ? "Bottom" : "Top"} ₹{num(data.pivot.price)}</div>
                <div className="tb-config-hint" style={{ margin: 0 }}>{fmtDate(data.pivot.date)} · {data.bars_since} days ago</div>
              </div>
              <div className="tb-summary-tile">
                <div className="tb-summary-label">MOVED SINCE ({data.direction.toUpperCase()})</div>
                <div className="tb-summary-value">₹{num(data.move)}</div>
                <div className="tb-config-hint" style={{ margin: 0 }}>A normal day ≈ ₹{num(data.atr)}</div>
              </div>
              <div className="tb-summary-tile">
                <div className="tb-summary-label">SPEED NOW</div>
                <div className="tb-summary-value">{Math.round(data.pace * 100)}%</div>
                <div className="tb-config-hint" style={{ margin: 0 }}>of a normal day, every day · stretched at 100%</div>
              </div>
              <div className="tb-summary-tile">
                <div className="tb-summary-label">LAST STRETCH</div>
                <div className="tb-summary-value">{data.thrust ? fmtDate(data.thrust.date) : "None"}</div>
                <div className="tb-config-hint" style={{ margin: 0 }}>
                  {data.thrust ? `${data.thrust.bars_ago} days ago · ${Math.round(data.thrust.pace * 100)}% speed${data.thrust.climax ? " · on heavy volume" : ""}` : "in this move"}
                </div>
              </div>
            </div>
          </section>

          <section className="card">
            <div className="dash-card-head">
              <div>
                <h2>{data.symbol}: past times it got stretched</h2>
                <p className="muted small">
                  It turned (made a new top or bottom) within 3 days in {data.own_record.turned} of these {data.own_record.thrusts} times.
                </p>
              </div>
            </div>
            {data.history.length === 0 ? (
              <p className="muted dash-empty">It never got stretched in the loaded history.</p>
            ) : (
              <div className="table-wrap">
                <table className="dash-signal-table">
                  <thead>
                    <tr><th>Date</th><th>Move</th><th className="num-cell">Days</th><th className="num-cell">Speed</th><th className="num-cell">Came back (normal days)</th><th>Turned within 3 days?</th></tr>
                  </thead>
                  <tbody>
                    {data.history.map((h) => (
                      <tr key={h.date + h.from_date}>
                        <td><span className="dash-two">{fmtDate(h.date)}<small>from {fmtDate(h.from_date)}</small></span></td>
                        <td><span className={h.direction === "up" ? "wk-up" : "wk-down"}>{h.direction}</span>{h.climax && <span className="th-climax">heavy volume</span>}</td>
                        <td className="num-cell">{h.bars}</td>
                        <td className="num-cell">{Math.round(h.pace * 100)}%</td>
                        <td className="num-cell">{h.back_atr == null ? "—" : `${h.back_atr.toFixed(1)}×`}</td>
                        <td>{h.turned == null ? <span className="muted small">too recent</span> : h.turned ? "Yes" : "No"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="muted small aw-honest">
              What 20 years of data say (613 stocks, indices and commodities): after a stock got stretched, it made a new top or bottom
              within 3 days about half the time ({data.record.turn_within_3}, against {data.record.turn_random} on an ordinary day), and it gave back
              about one normal day&apos;s move {data.record.back_1atr} of the time, usually in 1–2 days. But betting on that reversal made no
              money over time — so use it only as &quot;don&apos;t chase&quot;, not as a buy or sell signal.
            </p>
          </section>
        </>
      )}

      <p className="muted small aw-foot">
        Daily candles from Angel One. A turn counts once 10 days have closed after it.
        A normal day's range = the 14-day average true range (ATR). Heavy volume = a day of 1.5× the normal range on 1.5× the 20-day volume. For
        education only; not investment advice.
      </p>
    </div>
  );
}
