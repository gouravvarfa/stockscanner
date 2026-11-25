import { useEffect, useMemo, useRef, useState } from "react";
import { PageHero } from "../components/PageHero";
import { RatioChart } from "./ratio/RatioChart";
import { analyse, fromMonthPacked, ratioOf, type Pt, type RatioAnalysis } from "./ratio/ratioMath";

/**
 * Ratio Charts (2026-11-25): A / B ratios like Gold / Nifty from the end-of-day data, with where each stands in its own
 * history, what followed its zones in the past and a switch backtest - plus any two NSE stocks or ETFs as your own ratio.
 */
type Preset = { key: string; label: string; a: string; b: string; a_name: string; b_name: string; a_rows: Pt[]; b_rows: Pt[] };
type Built = { key: string; label: string; aName: string; bName: string; ratio: Pt[]; a: Pt[]; b: Pt[]; perYear: number; an: RatioAnalysis | null };

const pct = (x: number | null | undefined, d = 1) => (x == null || !Number.isFinite(x) ? "—" : `${x >= 0 ? "+" : ""}${(x * 100).toFixed(d)}%`);
const num = (x: number) => (x >= 100 ? x.toFixed(0) : x >= 1 ? x.toFixed(3) : x.toFixed(4));
const ym = (t: number) => new Date(t * 1000).toLocaleDateString("en-IN", { month: "short", year: "numeric" });

function build(key: string, label: string, aName: string, bName: string, a: Pt[], b: Pt[], perYear: number): Built {
  const ratio = ratioOf(a, b);
  return { key, label, aName, bName, ratio, a, b, perYear, an: analyse(ratio, a, b, perYear) };
}

function zoneText(b: Built): { cls: string; text: string } {
  const z = b.an?.zone;
  if (z === "high") return { cls: "rt-z-high", text: `${b.aName} expensive · favour ${b.bName}` };
  if (z === "low") return { cls: "rt-z-low", text: `${b.aName} cheap · favour ${b.aName}` };
  return { cls: "rt-z-mid", text: "Middle zone · no switch" };
}

function movingAvg(pts: Pt[], n: number): Pt[] {
  const out: Pt[] = [];
  let s = 0;
  pts.forEach((p, i) => {
    s += p[1];
    if (i >= n) s -= pts[i - n][1];
    if (i >= n - 1) out.push([p[0], s / n]);
  });
  return out;
}

function Detail({ b, dataAsOf }: { b: Built; dataAsOf: string }) {
  const an = b.an;
  const ma = useMemo(() => movingAvg(b.ratio, b.perYear === 52 ? 40 : 10), [b]);
  if (!an) return <div className="card"><p className="muted">Not enough history for this ratio (needs 2 years).</p></div>;
  const z = zoneText(b);
  const bt = an.backtest;
  const short = an.years < 6;
  return (
    <section className="card rt-detail">
      <div className="rt-detail-head">
        <div>
          <h2>{b.label}</h2>
          <p className="muted small" style={{ margin: 0 }}>
            {b.aName} ÷ {b.bName} · {b.perYear === 52 ? "weekly" : "monthly"} · {an.years.toFixed(1)} years of data · data of {dataAsOf ? new Date(`${dataAsOf}T00:00:00`).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }) : new Date(an.asOf * 1000).toLocaleDateString("en-IN")}
          </p>
        </div>
        <span className={`rt-zone ${z.cls}`}>{z.text}</span>
      </div>
      {short && <div className="notice-banner">Only {an.years.toFixed(1)} years of data — zones and backtest are less reliable than on the 15–20 year ratios.</div>}

      <RatioChart data={b.ratio} low={an.low} high={an.high} median={an.median} ma={ma} />
      <p className="muted small rt-legend">
        <span className="rt-key rt-key-high" /> High zone = top 15% of history · <span className="rt-key rt-key-low" /> Low zone = bottom 15% · dotted = {b.perYear === 52 ? "40-week" : "10-month"} average
      </p>

      <div className="rt-stats">
        <div className="rt-stat"><span>Ratio now</span><b>{num(an.now)}</b><small>median {num(an.median)}</small></div>
        <div className="rt-stat"><span>Where in its history</span><b>{an.pctRank.toFixed(0)}%</b>
          <i className="rt-bar"><i style={{ left: `${an.pctRank}%` }} /></i><small>0% = cheapest {b.aName} ever</small></div>
        <div className="rt-stat"><span>Z-score (3 years)</span><b>{an.z3y == null ? "—" : an.z3y.toFixed(2)}</b>
          <small>{an.z3y == null ? "" : Math.abs(an.z3y) >= 2 ? "far from normal" : Math.abs(an.z3y) >= 1 ? "stretched" : "near normal"}</small></div>
        <div className="rt-stat"><span>Trend</span><b>{an.trendUp == null ? "—" : an.trendUp ? `${b.aName} leading` : `${b.bName} leading`}</b>
          <small>ratio {an.trendUp ? "above" : "below"} its {b.perYear === 52 ? "40-week" : "10-month"} average</small></div>
        <div className="rt-stat"><span>Ratio change</span><b>{pct(an.chg.m12)}</b><small>last 12 months · 3M {pct(an.chg.m3)} · 1M {pct(an.chg.m1)}</small></div>
        <div className="rt-stat"><span>Zones</span><b>{num(an.low)} – {num(an.high)}</b><small>low – high</small></div>
      </div>

      <div className="rt-two">
        <div className="rt-box">
          <h3>What happened next (12 months)</h3>
          <table>
            <thead><tr><th>Ratio entered</th><th className="num-cell">Times</th><th className="num-cell">{b.aName}</th><th className="num-cell">{b.bName}</th><th className="num-cell">{b.bName} beat {b.aName}</th></tr></thead>
            <tbody>
              {([["High zone", an.afterHigh], ["Low zone", an.afterLow]] as const).map(([lab, s]) => (
                <tr key={lab}>
                  <td>{lab}</td>
                  {s ? (<><td className="num-cell">{s.times}</td><td className="num-cell">{pct(s.aAvg)}</td><td className="num-cell">{pct(s.bAvg)}</td><td className="num-cell">{(s.bBeatA * 100).toFixed(0)}%</td></>)
                    : <td colSpan={4} className="muted small">not yet in this zone (after the first 3 years)</td>}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted small">Average return of each side over the 12 months after the ratio moved into the zone. Zones as they were known at the time (no hindsight).</p>
        </div>
        <div className="rt-box">
          <h3>Switch backtest</h3>
          {bt ? (
            <>
              <table>
                <thead><tr><th>Since {ym(bt.from)}</th><th className="num-cell">CAGR</th><th className="num-cell">Worst fall</th><th className="num-cell">₹1 became</th></tr></thead>
                <tbody>
                  <tr className="rt-best"><td>Switch on the zones</td><td className="num-cell">{pct(bt.switchPerf.cagr)}</td><td className="num-cell">{pct(bt.switchPerf.maxDD, 0)}</td><td className="num-cell">₹{bt.switchPerf.growth.toFixed(2)}</td></tr>
                  <tr><td>Only {b.aName}</td><td className="num-cell">{pct(bt.a.cagr)}</td><td className="num-cell">{pct(bt.a.maxDD, 0)}</td><td className="num-cell">₹{bt.a.growth.toFixed(2)}</td></tr>
                  <tr><td>Only {b.bName}</td><td className="num-cell">{pct(bt.b.cagr)}</td><td className="num-cell">{pct(bt.b.maxDD, 0)}</td><td className="num-cell">₹{bt.b.growth.toFixed(2)}</td></tr>
                  <tr><td>50 / 50, monthly rebalance</td><td className="num-cell">{pct(bt.half.cagr)}</td><td className="num-cell">{pct(bt.half.maxDD, 0)}</td><td className="num-cell">₹{bt.half.growth.toFixed(2)}</td></tr>
                </tbody>
              </table>
              <p className="muted small">Hold {b.bName} when the ratio is in the high zone, {b.aName} in the low zone, keep the last pick in between. {bt.switches} switches · holding <b>{bt.holding === "A" ? b.aName : b.bName}</b> now. Before costs and taxes.</p>
            </>
          ) : <p className="muted small">Needs 4+ years of data.</p>}
        </div>
      </div>
    </section>
  );
}

export function RatioChartsPage() {
  const [presets, setPresets] = useState<Preset[] | null | undefined>(undefined);
  const [asOf, setAsOf] = useState("");
  const [sel, setSel] = useState<string>("gold_nifty");
  const [closes, setCloses] = useState<Record<string, number[]> | null>(null);
  const [loadingCloses, setLoadingCloses] = useState(false);
  const [aSym, setASym] = useState("");
  const [bSym, setBSym] = useState("NIFTYBEES");
  const [custom, setCustom] = useState<Built | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    fetch(`/eod/ratios.json?d=${new Date().toISOString().slice(0, 10)}`, { cache: "no-cache" })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => { setPresets(j?.presets ?? null); setAsOf(j?.data_as_of ?? ""); })
      .catch(() => setPresets(null));
  }, []);

  const built = useMemo(() => (presets ?? []).map((p) => build(p.key, p.label, p.a_name, p.b_name, p.a_rows, p.b_rows, 52)), [presets]);
  const current = sel === "custom" ? custom : built.find((b) => b.key === sel) ?? null;

  // the 2 MB list of monthly closes loads only when the user starts on their own ratio
  const closesReq = useRef<Promise<Record<string, number[]>> | null>(null);
  function loadCloses(): Promise<Record<string, number[]>> {
    if (closes) return Promise.resolve(closes);
    if (!closesReq.current) {
      setLoadingCloses(true);
      closesReq.current = fetch(`/eod/ratio_closes.json?d=${new Date().toISOString().slice(0, 10)}`, { cache: "no-cache" })
        .then((r) => (r.ok ? r.json() : null))
        .then((j) => (j?.symbols ?? {}) as Record<string, number[]>)
        .catch(() => ({}) as Record<string, number[]>)
        .then((m) => { setCloses(m); setLoadingCloses(false); return m; });
    }
    return closesReq.current;
  }
  const symbols = useMemo(() => (closes ? Object.keys(closes).sort() : []), [closes]);

  async function buildCustom() {
    const A = aSym.trim().toUpperCase(), B = bSym.trim().toUpperCase();
    const closes = await loadCloses();
    if (!closes[A] || !closes[B]) { setErr(`${!closes[A] ? A || "A" : B || "B"} not found — pick from the list (NSE symbols with 2+ years of data).`); return; }
    if (A === B) { setErr("Pick two different symbols."); return; }
    setErr("");
    setCustom(build("custom", `${A} / ${B}`, A, B, fromMonthPacked(closes[A]), fromMonthPacked(closes[B]), 12));
    setSel("custom");
  }

  return (
    <div className="page">
      <PageHero
        tone="ratio"
        eyebrow="Relative value · end-of-day"
        title="Ratio Charts"
        subtitle="One asset against another — Gold / Nifty, sectors / Nifty or any two stocks. Where the ratio stands in its own history, what followed its extremes and a switch backtest."
        motif={<RatioMotif />}
      >
        <span className="hero-pill">High zone = top 15% · low zone = bottom 15%</span>
        <span className="hero-pill hero-pill-soft">{asOf ? `NSE data of ${new Date(`${asOf}T00:00:00`).toLocaleDateString("en-IN", { day: "2-digit", month: "short" })}` : "Updated each evening"}</span>
      </PageHero>

      {presets === undefined ? (
        <div className="card state-block"><div className="tb-spinner" aria-hidden="true" /><div className="state-subtitle">Loading ratios…</div></div>
      ) : presets === null ? (
        <div className="card state-block"><div className="state-title">Ratio data is not available</div><div className="state-subtitle">It is built with the evening end-of-day update.</div></div>
      ) : (
        <>
          <div className="rt-grid">
            {built.map((b) => {
              const z = zoneText(b);
              return (
                <button key={b.key} type="button" className={`card rt-card${sel === b.key ? " active" : ""}`} onClick={() => setSel(b.key)}>
                  <span className="rt-card-title">{b.label}</span>
                  {b.an ? (
                    <>
                      <span className="rt-card-now"><b>{num(b.an.now)}</b><small className={b.an.chg.m12 != null && b.an.chg.m12 >= 0 ? "wk-up" : "wk-down"}>12M {pct(b.an.chg.m12, 0)}</small></span>
                      <i className="rt-bar"><i style={{ left: `${b.an.pctRank}%` }} /></i>
                      <span className={`rt-zone rt-zone-sm ${z.cls}`}>{z.text}</span>
                      <small className="muted">{b.an.years.toFixed(0)} yrs · {b.an.pctRank.toFixed(0)}% of history</small>
                    </>
                  ) : <small className="muted">not enough data</small>}
                </button>
              );
            })}
          </div>

          <div className="card">
            <div className="run-row">
              <div className="tb-config-grid">
                <div className="tb-field">
                  <label>A (top)
                    <input list="rt-syms" value={aSym} placeholder="e.g. HDFCBANK" onFocus={() => void loadCloses()} onChange={(e) => { void loadCloses(); setASym(e.target.value.toUpperCase()); }} />
                  </label>
                </div>
                <div className="tb-field">
                  <label>B (bottom)
                    <input list="rt-syms" value={bSym} placeholder="e.g. NIFTYBEES" onFocus={() => void loadCloses()} onChange={(e) => { void loadCloses(); setBSym(e.target.value.toUpperCase()); }} />
                  </label>
                </div>
              </div>
              <div className="tb-actions">
                <button type="button" className="tb-btn tb-btn-primary" onClick={() => void buildCustom()} disabled={loadingCloses || !aSym || !bSym}>
                  {loadingCloses ? "Loading list…" : "Build ratio"}
                </button>
                <span className="tb-config-hint">Your own ratio: any two NSE stocks or ETFs (monthly, adjusted for splits and bonuses). Nifty = NIFTYBEES, Gold = GOLDBEES, Bank Nifty = BANKBEES.</span>
              </div>
            </div>
            <datalist id="rt-syms">{symbols.map((s) => <option key={s} value={s} />)}</datalist>
            {err && <p className="muted small" style={{ color: "var(--danger, #dc2626)", marginBottom: 0 }}>{err}</p>}
          </div>

          {current && <Detail key={current.key + current.label} b={current} dataAsOf={asOf} />}
        </>
      )}
    </div>
  );
}

function RatioMotif() {
  return (
    <svg viewBox="0 0 200 150" className="motif-svg">
      <line x1="10" y1="35" x2="190" y2="35" className="m-line" strokeDasharray="4 4" />
      <line x1="10" y1="115" x2="190" y2="115" className="m-line" strokeDasharray="4 4" />
      <polyline points="10,100 30,80 45,90 60,50 75,38 90,60 105,95 120,112 135,100 150,70 165,45 180,40 190,60" className="m-line m-diamond" fill="none" />
      <text x="190" y="28" className="m-rashi" textAnchor="end">A / B</text>
    </svg>
  );
}
