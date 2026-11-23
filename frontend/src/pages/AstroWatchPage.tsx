import { useState } from "react";
import data from "../data/astroWatch.json";
import nifty from "../data/niftyDates.json";
import { PageHero, VedicKundali } from "../components/PageHero";

/**
 * Astro Watch: the astro and calendar dates that held up in our backtests, each with its measured record.
 * - Nifty dates: windows when Nifty went up far more often than usual (tested 2008-2025 in two halves + Sensex 1997+).
 * - Gold / Silver / Crude: the Shukra-Mangal yuti (Venus-Mars conjunction) comes with bigger-than-usual moves.
 * 2026-11-23: jyotish look (rashi chakra, graha glyphs, gold/saffron), in the app's own theme.
 */

type Asset = "gold" | "silver" | "crude";
type Ev = { date: string; rashi: string } & Partial<Record<Asset, number>>;
const ASSETS: { key: Asset; label: string }[] = [
  { key: "gold", label: "Gold" },
  { key: "silver", label: "Silver" },
  { key: "crude", label: "Crude" },
];
const events = data.events as Ev[];
const summary = data.summary as Record<Asset, { avg_ratio: number; bigger_than_normal_pct: number; n: number; normal_5d_move_pct: number }>;

type NiftyEvent = {
  date: string; days: number; name: string; tradition: string; times: number; up: number; normal: number;
  early: number; late: number; sensex: number; sensex_times: number; avg_move: number;
};
const niftyEvents = nifty.events as NiftyEvent[];

const fmt = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
const inDays = (iso: string) => Math.ceil((new Date(`${iso}T00:00:00`).getTime() - Date.now()) / 86400000);
const median = (xs: number[]) => {
  const s = [...xs].sort((a, b) => a - b);
  return s.length ? (s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2) : 0;
};
const todayIso = () => new Date().toISOString().slice(0, 10);

/** The graha (or season) for an event: its Devanagari mark and name. */
function glyphOf(name: string): { glyph: string; kind: "graha" | "surya" | "calendar"; hindi: string } {
  if (/Mangal|Mars/i.test(name)) return { glyph: "मं", kind: "graha", hindi: "मंगल वक्री" };
  if (/Shukra|Venus/i.test(name)) return { glyph: "शु", kind: "graha", hindi: "शुक्र वक्री" };
  if (/equinox/i.test(name)) return { glyph: "सू", kind: "surya", hindi: "सूर्य · मेष संक्रमण" };
  if (/solstice/i.test(name)) return { glyph: "सू", kind: "surya", hindi: "सूर्य · कर्क संक्रमण" };
  return { glyph: "ऋतु", kind: "calendar", hindi: "ऋतु काल" };
}

function Medallion({ glyph, kind, big = false }: { glyph: string; kind: string; big?: boolean }) {
  return <span className={`aw-medal aw-medal-${kind}${big ? " aw-medal-big" : ""}`}>{glyph}</span>;
}

/** How often it worked, against an ordinary window (the tick). */
function HitMeter({ up, normal }: { up: number; normal: number }) {
  return (
    <span className="aw-meter" title={`${up}% vs ${normal}% on an ordinary window`}>
      <span className="aw-meter-fill" style={{ width: `${up}%` }} />
      <i className="aw-meter-tick" style={{ left: `${normal}%` }} />
    </span>
  );
}

/* ------------------------------------------------------------ Nifty dates */
function NiftyView() {
  const upcoming = niftyEvents.filter((e) => e.date >= todayIso());
  const next = upcoming[0];
  const byMonth = new Map<string, NiftyEvent[]>();
  for (const e of upcoming.slice(next ? 1 : 0)) {
    const k = new Date(`${e.date}T00:00:00`).toLocaleDateString("en-IN", { month: "long", year: "numeric" });
    byMonth.set(k, [...(byMonth.get(k) ?? []), e]);
  }
  return (
    <>
      {next && (() => {
        const g = glyphOf(next.name);
        return (
          <section className="card aw-feature">
            <div className="aw-feature-main">
              <Medallion glyph={g.glyph} kind={g.kind} big />
              <div>
                <span className="aw-kicker">अगला मुहूर्त · Next window · in {inDays(next.date)} days</span>
                <div className="aw-date">{fmt(next.date)}</div>
                <div className="aw-hindi">{g.hindi}</div>
                <div className="aw-name">{next.name}</div>
                <span className="aw-chip">{next.tradition}</span>
              </div>
            </div>
            <div className="aw-feature-stat">
              <div className="aw-big-pct">{next.up}%</div>
              <div className="muted small">Nifty up over the next {next.days} trading days</div>
              <HitMeter up={next.up} normal={next.normal} />
              <div className="aw-record">
                <span>{next.times} past times · ordinary window {next.normal}%</span>
                <span>2008–16 {next.early}% · 2017–25 {next.late}% · Sensex {next.sensex}% of {next.sensex_times}</span>
              </div>
            </div>
          </section>
        );
      })()}

      <section className="card">
        <div className="dash-card-head">
          <div>
            <h2><span className="aw-deva">आगामी मुहूर्त</span> Upcoming windows</h2>
            <p className="muted small">The bar is how often Nifty was up in that window before; the tick marks an ordinary window.</p>
          </div>
        </div>
        <div className="aw-timeline">
          {[...byMonth.entries()].map(([month, list]) => (
            <div key={month} className="aw-month">
              <div className="aw-month-name">{month}</div>
              {list.map((e) => {
                const g = glyphOf(e.name);
                const d = new Date(`${e.date}T00:00:00`);
                return (
                  <div key={`${e.date}-${e.name}`} className="aw-item">
                    <div className="aw-day">
                      <b>{d.getDate()}</b>
                      <span>{d.toLocaleDateString("en-IN", { weekday: "short" })}</span>
                    </div>
                    <Medallion glyph={g.glyph} kind={g.kind} />
                    <div className="aw-item-text">
                      <span className="aw-item-name"><span className="aw-deva-sm">{g.hindi}</span>{e.name}</span>
                      <span className="aw-item-sub">{e.tradition} · next {e.days} trading days · {e.times} past times</span>
                    </div>
                    <div className="aw-item-stat">
                      <span className="aw-hit">{e.up}%</span>
                      <HitMeter up={e.up} normal={e.normal} />
                    </div>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
        <p className="muted small aw-honest">
          Ordinarily Nifty is up over 20 trading days about 60% of the time and over 5 days about 56%. Several windows are
          the same season (the June solstice and weeks 25–26). With 10–20 past cases each, some can be chance — use them
          with your own setup and a stop-loss.
        </p>
      </section>
    </>
  );
}

/* ------------------------------------------------------------ Gold / Silver / Crude */
function MetalsView() {
  const upcoming = events.filter((e) => e.date >= todayIso());
  const past = events.filter((e) => e.gold !== undefined).reverse();
  const next = upcoming[0];
  return (
    <>
      {next && (
        <section className="card aw-feature">
          <div className="aw-feature-main">
            <Medallion glyph="शु·मं" kind="yuti" big />
            <div>
              <span className="aw-kicker">शुक्र–मंगल युति · Next yuti · in {inDays(next.date)} days</span>
              <div className="aw-date">{fmt(next.date)}</div>
              <div className="aw-name">Venus–Mars conjunction</div>
              <span className="aw-chip">{next.rashi} rashi</span>
            </div>
          </div>
          <div className="aw-feature-stat">
            <div className="aw-use">
              <b>A bigger move, no direction</b>
              <span>Option buyers: a bigger move is more likely than usual. Futures / swing: keep the stop-loss a little wider, or size smaller.</span>
            </div>
            {upcoming.length > 1 && (
              <div className="aw-record"><span>After that: {upcoming.slice(1, 5).map((e) => fmt(e.date)).join(" · ")}</span></div>
            )}
          </div>
        </section>
      )}

      <section className="card">
        <div className="dash-card-head">
          <div>
            <h2>How it did before</h2>
            <p className="muted small">
              Move in the 5 trading days after each yuti against that market&apos;s normal 5-day move (1.0× = a normal week) ·{" "}
              {past.length} yutis, {past[past.length - 1] ? fmt(past[past.length - 1].date) : ""} to {past[0] ? fmt(past[0].date) : ""}
            </p>
          </div>
        </div>
        <div className="tb-summary-grid wk-kpis">
          {ASSETS.map(({ key, label }) => {
            const vals = past.map((e) => e[key]).filter((v): v is number => v !== undefined);
            return (
              <div key={key} className="tb-summary-tile">
                <div className="tb-summary-label">{label.toUpperCase()}</div>
                <div className="tb-summary-value">{summary[key].avg_ratio.toFixed(2)}× <span className="aw-unit">average</span></div>
                <div className="tb-config-hint" style={{ margin: 0 }}>
                  median {median(vals).toFixed(2)}× · bigger than normal {summary[key].bigger_than_normal_pct}% of the time
                </div>
              </div>
            );
          })}
        </div>
        <p className="muted small aw-honest">
          The average is pulled up by a few very big weeks; in a typical yuti week the move is about normal. Treat it as a
          watch window, never as a trade signal on its own.
        </p>
        <div className="table-wrap" style={{ marginTop: 12 }}>
          <table className="dash-signal-table">
            <thead>
              <tr>
                <th>Yuti date</th>
                <th>Rashi</th>
                {ASSETS.map((a) => <th key={a.key} className="num-cell">{a.label}</th>)}
              </tr>
            </thead>
            <tbody>
              {past.map((e) => (
                <tr key={e.date}>
                  <td>{fmt(e.date)}</td>
                  <td><span className="aw-chip aw-chip-sm">{e.rashi}</span></td>
                  {ASSETS.map(({ key }) => {
                    const v = e[key];
                    return (
                      <td key={key} className={`num-cell ${v === undefined ? "muted" : v >= 1.5 ? "aw-big" : v >= 1 ? "" : "muted"}`}>
                        {v === undefined ? "—" : `${v.toFixed(2)}×`}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}

export function AstroWatchPage() {
  const [tab, setTab] = useState<"nifty" | "metals">("nifty");
  const next = niftyEvents.find((e) => e.date >= todayIso());
  return (
    <div className="page astro-page">
      <PageHero
        tone="astro"
        eyebrow="ज्योतिष · Vedic Jyotish"
        title="Astro Watch"
        subtitle="Graha and calendar windows that held up in our backtests, each with its record. They tell you when to watch, never what to buy."
        motif={<VedicKundali />}
      >
        {next && <span className="hero-pill">Next: {fmt(next.date)} · {next.name.split(" (")[0]}</span>}
        <span className="hero-pill hero-pill-soft">Sidereal (Lahiri) · tested 2008–2025</span>
      </PageHero>

      <div className="aw-seg" role="tablist" aria-label="Market">
        <button type="button" role="tab" aria-selected={tab === "nifty"} className={tab === "nifty" ? "active" : ""} onClick={() => setTab("nifty")}>
          <span className="aw-seg-glyph">सू</span> Nifty muhurat
        </button>
        <button type="button" role="tab" aria-selected={tab === "metals"} className={tab === "metals" ? "active" : ""} onClick={() => setTab("metals")}>
          <span className="aw-seg-glyph">शु·मं</span> Gold · Silver · Crude
        </button>
      </div>
      {tab === "nifty" ? <NiftyView /> : <MetalsView />}

      <p className="muted small aw-foot">
        Dates are astronomy (fixed in advance; rashi in the sidereal Lahiri zodiac). Records: Nifty and Sensex daily
        closes; COMEX Gold, Silver and WTI Crude futures. For education only; not investment advice.
      </p>
    </div>
  );
}
