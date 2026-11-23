import { useState } from "react";
import data from "../data/astroWatch.json";
import nifty from "../data/niftyDates.json";

/**
 * Astro Watch (2026-11-22): the one astro signal that held up in our backtests (10 markets, 2000-2026) - the
 * Shukra-Mangal yuti (Venus-Mars conjunction) comes with bigger-than-usual moves in Gold, Silver and Crude over the
 * next 5 trading days. It gives NO direction. The dates are astronomy (fixed in advance); the history is measured.
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

const fmt = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
const median = (xs: number[]) => {
  const s = [...xs].sort((a, b) => a - b);
  return s.length ? (s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2) : 0;
};

function MetalsView() {
  const today = new Date().toISOString().slice(0, 10);
  const upcoming = events.filter((e) => e.date >= today);
  const past = events.filter((e) => e.gold !== undefined).reverse();
  const next = upcoming[0];
  const daysLeft = next ? Math.ceil((new Date(`${next.date}T00:00:00`).getTime() - Date.now()) / 86400000) : null;

  return (
    <>
      <p className="muted small aw-intro">
        Shukra–Mangal yuti (Venus–Mars conjunction): a warning that Gold, Silver and Crude may move more than usual in
        the next 5 trading days. It never says up or down.
      </p>

      <section className="card aw-next">
        <div className="dash-card-head">
          <div>
            <h2>Next yuti</h2>
            <p className="muted small">The watch window is the yuti day and the 5 trading days after it</p>
          </div>
        </div>
        {next ? (
          <div className="aw-next-row">
            <div>
              <div className="aw-date">{fmt(next.date)}</div>
              <div className="muted small">in {next.rashi} rashi · {daysLeft} days from today</div>
            </div>
            <div className="aw-use">
              <b>How to use it</b>
              <span>Option buyers: a bigger move is more likely than usual. Futures / swing: keep the stop-loss a little wider, or size smaller.</span>
            </div>
          </div>
        ) : (
          <p className="muted">No yuti in the saved dates.</p>
        )}
        {upcoming.length > 1 && (
          <p className="muted small aw-later">
            After that: {upcoming.slice(1, 7).map((e) => fmt(e.date)).join(" · ")}
          </p>
        )}
      </section>

      <section className="card">
        <div className="dash-card-head">
          <div>
            <h2>How it did before</h2>
            <p className="muted small">
              Move in the 5 trading days after each yuti, against that market's normal 5-day move (1.0× = a normal week).
              {` `}{past.length} yutis, {past[past.length - 1] ? fmt(past[past.length - 1].date) : ""} to {past[0] ? fmt(past[0].date) : ""}.
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
          Honest reading: the average is pulled up by a few very big weeks; in a typical yuti week the move is about
          normal. Treat it as a watch window, never as a trade signal on its own.
        </p>

        <div className="table-wrap" style={{ marginTop: 12 }}>
          <table className="dash-signal-table">
            <thead>
              <tr>
                <th>Yuti date</th>
                <th>Rashi</th>
                {ASSETS.map((a) => (
                  <th key={a.key} className="num-cell">{a.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {past.map((e) => (
                <tr key={e.date}>
                  <td>{fmt(e.date)}</td>
                  <td className="muted">{e.rashi}</td>
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

      <p className="muted small">
        Dates: astronomical Venus–Mars conjunctions (rashi in the sidereal Lahiri zodiac). Markets: COMEX Gold, Silver and
        WTI Crude futures, data to {fmt(data.data_to)}. Tested with 50+ other Vedic factors across 10 markets; this was
        the only one worth watching. For education only; not investment advice.
      </p>
    </>
  );
}


/* ------------------------------------------------------------ Nifty dates (2026-11-23) */
type NiftyEvent = {
  date: string; days: number; name: string; tradition: string; times: number; up: number; normal: number;
  early: number; late: number; sensex: number; sensex_times: number; avg_move: number;
};
const niftyEvents = nifty.events as NiftyEvent[];
const inDays = (iso: string) => Math.ceil((new Date(`${iso}T00:00:00`).getTime() - Date.now()) / 86400000);

function NiftyView() {
  const today = new Date().toISOString().slice(0, 10);
  const upcoming = niftyEvents.filter((e) => e.date >= today);
  const next = upcoming[0];
  return (
    <>
      <p className="muted small aw-intro">
        Dates when Nifty went up far more often than usual over the following days (tested 2008–2025, checked again on
        Sensex since 1997). They point to a time window, not a guarantee — use them with your own setup and a stop-loss.
      </p>
      {next && (
        <section className="card aw-next">
          <div className="dash-card-head">
            <div>
              <h2>Next Nifty date</h2>
              <p className="muted small">{next.tradition}</p>
            </div>
          </div>
          <div className="aw-next-row">
            <div>
              <div className="aw-date">{fmt(next.date)}</div>
              <div className="muted small">{next.name} · in {inDays(next.date)} days</div>
            </div>
            <div className="aw-use aw-use-up">
              <b>Up {next.up}% of the time over the next {next.days} trading days</b>
              <span>
                {next.times} past times on Nifty (normal: {next.normal}%) · 2008–16 {next.early}% · 2017–25 {next.late}% ·
                Sensex {next.sensex}% of {next.sensex_times}
              </span>
            </div>
          </div>
        </section>
      )}
      <section className="card">
        <div className="dash-card-head">
          <div>
            <h2>Upcoming Nifty dates</h2>
            <p className="muted small">Each row: the date, how many trading days after it, and how often Nifty was up in that window before.</p>
          </div>
        </div>
        <div className="table-wrap">
          <table className="dash-signal-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>What</th>
                <th className="num-cell">Window</th>
                <th className="num-cell">Nifty up</th>
                <th className="num-cell">2008–16 / 2017–25</th>
                <th className="num-cell">Sensex up</th>
                <th className="num-cell">Avg move</th>
              </tr>
            </thead>
            <tbody>
              {upcoming.map((e) => (
                <tr key={`${e.date}-${e.name}`}>
                  <td><span className="dash-two">{fmt(e.date)}<small>in {inDays(e.date)} days</small></span></td>
                  <td><span className="dash-two">{e.name}<small>{e.tradition}</small></span></td>
                  <td className="num-cell">{e.days} days</td>
                  <td className="num-cell"><span className="aw-hit">{e.up}%</span> <small className="muted">of {e.times}</small></td>
                  <td className="num-cell muted">{e.early}% / {e.late}%</td>
                  <td className="num-cell muted">{e.sensex}% <small>of {e.sensex_times}</small></td>
                  <td className="num-cell">{e.avg_move > 0 ? "+" : ""}{e.avg_move}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted small aw-honest">
          Normally Nifty is up over 20 trading days about 60% of the time and over 5 days about 56%. Several rows are the
          same season (the June solstice and weeks 25–26). With 10–20 past cases each, some of these can be chance.
        </p>
      </section>
    </>
  );
}

export function AstroWatchPage() {
  const [tab, setTab] = useState<"nifty" | "metals">("nifty");
  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Astro Watch</h1>
          <p className="page-subtitle">Astro and calendar dates that held up in our backtests, with their record.</p>
        </div>
      </div>
      <div className="tabs aw-tabs" role="tablist" aria-label="Market">
        <button type="button" role="tab" aria-selected={tab === "nifty"} className={tab === "nifty" ? "tab active" : "tab"} onClick={() => setTab("nifty")}>
          Nifty dates
        </button>
        <button type="button" role="tab" aria-selected={tab === "metals"} className={tab === "metals" ? "tab active" : "tab"} onClick={() => setTab("metals")}>
          Gold · Silver · Crude
        </button>
      </div>
      {tab === "nifty" ? <NiftyView /> : <MetalsView />}
    </div>
  );
}
