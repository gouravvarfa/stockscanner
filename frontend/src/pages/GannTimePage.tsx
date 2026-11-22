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
import { GannChart } from "./gannTime/GannChart";
import "./gannTime/gannTime.css";

const fmtDate = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
const fmtPrice = (v: number) => v.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmtPct = (v: number | null) => (v === null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(1)}%`);
const stars = (n: number) => "★".repeat(Math.min(n - 1, 3));

function whenLabel(barsAway: number): string {
  if (barsAway < 0) return `Window chalu (${-barsAway} din pehle)`;
  if (barsAway === 0) return "Aaj";
  if (barsAway === 1) return "Kal";
  return `${barsAway} din baad`;
}

function ClusterCell({ c }: { c: GannCluster }) {
  return (
    <div>
      <div>{fmtDate(c.date)}</div>
      <div className={c.bars_away <= 1 ? "gt-when gt-when-now" : "gt-when"}>{whenLabel(c.bars_away)}</div>
    </div>
  );
}

/* ------------------------------------------------------------ strong sectors */
function SectorView({ onOpen }: { onOpen: (symbol: string) => void }) {
  const [data, setData] = useState<GannSectorScan | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function start(fresh: boolean) {
    setError(null);
    try {
      setData(await startGannSectors(fresh));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Scan start nahi hua.");
    }
  }
  // Opening the page only shows the last result (if any); a scan starts only on "Run scan".
  useEffect(() => {
    getGannSectors().then(setData).catch((e) => setError(e instanceof Error ? e.message : "Data nahi mila."));
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
      <div className="card">
        <div className="tb-actions">
          <button type="button" className="tb-btn tb-btn-primary" onClick={() => void start(true)} disabled={running}>
            {running ? "Scanning…" : "Run scan"}
          </button>
          {(!data || data.status === "idle") && (
            <span className="tb-config-hint">Run scan dabao — A Group ke ~600 stocks check honge (kuch minute lagenge).</span>
          )}
          {data?.status === "done" && data.finished_at && (
            <span className="tb-config-hint">
              {data.rows.length} stocks · {strong.length} strong sectors · updated {new Date(`${data.finished_at}Z`).toLocaleString("en-IN")}
              {data.failed > 0 ? ` · ${data.failed} stocks had no data` : ""}
            </span>
          )}
        </div>
        {running && (
          <div className="gt-progress-wrap">
            <div className="state-subtitle">A Group stocks check ho rahe hain… {data?.processed} / {data?.total} ({pct}%) · list beech mein bhi bharti rahegi</div>
            <div className="gt-progress"><div style={{ width: `${pct}%` }} /></div>
          </div>
        )}
      </div>

      {(error || data?.status === "error") && (
        <div className="card state-block">
          <div className="state-title">Kuch galat hua</div>
          <div className="state-subtitle">{error ?? data?.error}</div>
        </div>
      )}

      {data && data.status !== "error" && data.status !== "idle" && (
        <div className="card">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Company</th>
                  <th>Sector</th>
                  <th>Agli date</th>
                  <th>Strength</th>
                  <th>Uske baad</th>
                  <th className="num-cell">Price</th>
                  <th>Note</th>
                  <th>Chart</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((r, i) => (
                  <tr key={r.symbol}>
                    <td>{i + 1}</td>
                    <td><span className="gt-name">{r.company_name}</span><div className="muted small">{r.symbol}</div></td>
                    <td>{r.sector}</td>
                    <td><ClusterCell c={r.clusters[0]} /></td>
                    <td className="gt-stars" title={`${r.clusters[0].strength} projections`}>{stars(r.clusters[0].strength)}</td>
                    <td className="muted small">{r.clusters[1] ? fmtDate(r.clusters[1].date) : "—"}</td>
                    <td className="num-cell">{fmtPrice(r.close)}</td>
                    <td className="small">{r.new_swing_forming ? <span className="gt-warn">Naya swing ban raha hai</span> : ""}</td>
                    <td><button type="button" className="tb-btn tb-btn-secondary" onClick={() => onOpen(r.symbol)}>Open</button></td>
                  </tr>
                ))}
                {data.rows.length === 0 && (
                  <tr><td colSpan={9} className="gt-empty">{running ? "Abhi tak koi stock nahi mila — check chal raha hai." : "Strong sectors mein agle 3 mahine koi cluster date nahi hai."}</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {data && data.sectors.length > 0 && (
        <div className="card gt-act-card">
          <div className="act-top">
            <h2 style={{ margin: 0 }}>Sector strength</h2>
            <span className="muted small">vs NIFTY: 1M {fmtPct(data.nifty_1m)}, 3M {fmtPct(data.nifty_3m)}</span>
          </div>
          <div className="gt-act-grid">
            {[
              { tone: "watch", title: "Strong sectors", list: data.sectors.filter((s) => s.strong), note: "NIFTY se tez (median 1M + 3M return − NIFTY); top 3 hamesha strong. Inke stocks upar list mein hain." },
              { tone: "weak", title: "Baaki sectors", list: data.sectors.filter((s) => !s.strong), note: "NIFTY se peeche. 3 se kam stock wale sector nahi gine jaate." },
            ].map((b) => (
              <div key={b.tone} className={`act-box act-${b.tone}`}>
                <div className="act-head">
                  <span className="act-name">{b.title}</span>
                  <span className="act-count">{b.list.length}</span>
                </div>
                <p className="act-note">{b.note}</p>
                {b.list.length === 0 ? <p className="act-empty">Koi nahi</p> : (
                  <ul className="act-items">
                    {b.list.map((s) => (
                      <li key={s.sector}>
                        <span className="act-main">{s.sector}</span>
                        <span className="act-sub">{s.stocks} stocks · 1M {fmtPct(s.ret_1m)} · 3M {fmtPct(s.ret_3m)}</span>
                        <span className={s.strong ? "act-val gt-pos" : "act-val gt-neg"}>{fmtPct(s.score)}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        </div>
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

  useEffect(() => {
    const q = query.trim();
    if (!q || q.toUpperCase() === symbol) { setHits([]); return; }
    const id = window.setTimeout(() => { searchGannStocks(q).then(setHits).catch(() => setHits([])); }, 200);
    return () => window.clearTimeout(id);
  }, [query, symbol]);

  useEffect(() => {
    if (!symbol) return;
    setQuery(symbol);
    setLoading(true);
    setError(null);
    getGannStock(symbol)
      .then(setData)
      .catch((e) => { setData(null); setError(e instanceof Error ? e.message : "Data nahi mila."); })
      .finally(() => setLoading(false));
  }, [symbol]);

  const futureProjections = useMemo(() => (data?.projections ?? []).slice().sort((a, b) => a.bars_away - b.bars_away), [data]);

  return (
    <>
      <div className="card">
        <div className="gt-search">
          <input
            type="search"
            placeholder="NSE ka koi bhi stock — naam ya symbol (jaise Reliance, DIVISLAB)"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && hits[0]) onPick(hits[0].symbol); }}
            aria-label="Search NSE stock"
          />
          {hits.length > 0 && (
            <div className="gt-hits">
              {hits.map((h) => (
                <button type="button" key={h.symbol} onClick={() => onPick(h.symbol)}>
                  <span className="gt-name">{h.symbol}</span> <span className="muted small">{h.company_name}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {loading && <div className="card state-block"><div className="state-title">{symbol} ka data aa raha hai…</div></div>}
      {error && <div className="card state-block"><div className="state-title">Kuch galat hua</div><div className="state-subtitle">{error}</div></div>}

      {data && !loading && (
        <>
          <div className="card">
            <div className="gt-stock-head">
              <div>
                <h2 className="gt-h2">{data.company_name}</h2>
                <div className="muted small">{data.symbol}{data.sector ? ` · ${data.sector}` : ""} · last candle {fmtDate(data.last_date)} · {fmtPrice(data.last_close)}</div>
              </div>
              {data.new_swing_forming && <span className="gt-warn">⚠ Naya swing ban raha hai — dates badal sakti hain</span>}
            </div>
            <GannChart data={data} />
            <div className="muted small gt-legend">Neeli line = swings (pahaad / ghaati). Laal patti = cluster date, halki laal = ±3 candle window.</div>
          </div>

          <div className="gt-grid">
            <div className="card">
              <h3 className="gt-h3">Candle ginti</h3>
              <table>
                <thead><tr><th>Se</th><th>Tak</th><th className="num-cell">Candles</th></tr></thead>
                <tbody>
                  {data.counts.map((c) => (
                    <tr key={c.from_date}>
                      <td>{c.from_kind === "H" ? "Pahaad" : "Ghaati"} · {fmtDate(c.from_date)}</td>
                      <td>{c.to_kind === "H" ? "Pahaad" : "Ghaati"} · {fmtDate(c.to_date)}</td>
                      <td className="num-cell">{c.candles}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="card">
              <h3 className="gt-h3">Sabhi projections (agle 3 mahine)</h3>
              <div className="gt-proj-list">
                {futureProjections.map((p, i) => (
                  <div key={i} className="gt-proj">
                    <span>{fmtDate(p.date)}</span>
                    <span className="muted small">{p.label} · {p.count} candles ({fmtDate(p.source_date)} se)</span>
                  </div>
                ))}
                {futureProjections.length === 0 && <div className="muted small">Koi projection nahi.</div>}
              </div>
            </div>
          </div>

          <div className="card gt-act-card">
            <div className={`act-box act-${data.clusters.length ? "watch" : "weak"}`}>
              <div className="act-head">
                <span className="act-name">Cluster dates</span>
                <span className="act-count">{data.clusters.length}</span>
              </div>
              <p className="act-note">Jahan 2 ya zyada projections ±2 candle mein milein. Palta ±3 candle ke window mein kabhi bhi aa sakta hai — entry tab lo jab candle ya RSI bhi palta dikhaye.</p>
              {data.clusters.length === 0 ? (
                <p className="act-empty">Agle 3 mahine koi cluster nahi — sirf akeli dates hain, unki value nahi.</p>
              ) : (
                <ul className="act-items">
                  {data.clusters.map((c) => (
                    <li key={c.date}>
                      <span className="act-main">{fmtDate(c.date)} · <span className={c.bars_away <= 1 ? "gt-when gt-when-now" : "gt-when"}>{whenLabel(c.bars_away)}</span></span>
                      <span className="act-sub">{c.projections.map((p) => `${p.label} of ${p.count} candles`).join(" · ")}</span>
                      <span className="act-val gt-stars">{stars(c.strength)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </>
      )}
    </>
  );
}

/* ------------------------------------------------------------ page */
export function GannTimePage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") === "stock" ? "stock" : "sectors";
  const symbol = (params.get("symbol") ?? "").toUpperCase();

  const openStock = (s: string) => setParams({ tab: "stock", symbol: s });

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Gann Square · Time Dates</h1>
          <p className="page-subtitle">
            Swing ki candles gin kar aage ki turn dates (Gann time cycle). Akeli date ki value nahi — sirf cluster dates dikhti hain,
            agle 3 mahine tak. Yeh &quot;kab&quot; batata hai, &quot;kidhar&quot; nahi.
          </p>
        </div>
      </div>

      <div className="gt-tabs" role="tablist">
        <button type="button" role="tab" aria-selected={tab === "sectors"} className={tab === "sectors" ? "active" : ""} onClick={() => setParams({ tab: "sectors" })}>
          Strong sectors
        </button>
        <button type="button" role="tab" aria-selected={tab === "stock"} className={tab === "stock" ? "active" : ""} onClick={() => setParams(symbol ? { tab: "stock", symbol } : { tab: "stock" })}>
          Ek stock
        </button>
      </div>

      {tab === "sectors" ? <SectorView onOpen={openStock} /> : <StockView symbol={symbol} onPick={openStock} />}
    </div>
  );
}
