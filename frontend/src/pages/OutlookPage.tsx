import { useEffect, useState } from "react";
import { BellCurveMotif, PageHero } from "../components/PageHero";
import { OUTLOOK_EVENTS, type OutlookEvent, type OutlookEventKind } from "../data/outlookEvents";
import record from "../data/outlookRecord.json";
import niftyDates from "../data/niftyDates.json";
import { getOutlook, type OutlookRange, type OutlookSnapshot } from "../services/outlookApi";

/**
 * Outlook (2026-11-23): the next week and month as probabilities and ranges, never as a call.
 * 1) Nifty's range from India VIX, with how often Nifty actually stayed inside it (2008-2026)
 * 2) Market weather today and what followed the same weather before
 * 3) Gold / Silver ranges from their recent volatility
 * 4) Known events of the next 90 days, 5) month seasonality.
 */

const SAVED = "outlook:last";
const num = (v: number, d = 0) => v.toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d });
const fmt = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
const MONTH = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
type Weather = { trend: string; vix: string; days: number; up20: number; avg20: number; worst20: number };
type Season = Record<string, { up: number; avg: number; years: number }>;

const KIND: Record<OutlookEventKind, { label: string; cls: string }> = {
  rbi: { label: "RBI", cls: "ol-k-rbi" }, fed: { label: "US Fed", cls: "ol-k-fed" }, budget: { label: "Budget", cls: "ol-k-budget" },
  expiry: { label: "Expiry", cls: "ol-k-expiry" }, results: { label: "Results", cls: "ol-k-results" },
  holiday: { label: "Holiday", cls: "ol-k-holiday" }, astro: { label: "Astro", cls: "ol-k-astro" },
};

/** Price ladder: the 2-sigma band, the 1-sigma band inside it, and today's price in the middle. */
function RangeBar({ r, digits = 0, unit = "" }: { r: OutlookRange; digits?: number; unit?: string }) {
  return (
    <div className="ol-range">
      <div className="ol-range-track">
        <span className="ol-band-2" />
        <span className="ol-band-1" />
        <i className="ol-now" />
      </div>
      <div className="ol-range-labels">
        <span>{unit}{num(r.low_2s, digits)}</span>
        <b>{unit}{num(r.low_1s, digits)}</b>
        <b>{unit}{num(r.high_1s, digits)}</b>
        <span>{unit}{num(r.high_2s, digits)}</span>
      </div>
    </div>
  );
}

export function OutlookPage() {
  const [data, setData] = useState<OutlookSnapshot | null>(() => {
    try { return JSON.parse(localStorage.getItem(SAVED) ?? "null") as OutlookSnapshot | null; } catch { return null; }
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const refresh = () => {
    setLoading(true); setError(null);
    getOutlook()
      .then((d) => { setData(d); try { localStorage.setItem(SAVED, JSON.stringify(d)); } catch { /* full */ } })
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load the outlook."))
      .finally(() => setLoading(false));
  };
  useEffect(refresh, []);

  const weather = (record.weather as Weather[]).find((w) => data && w.trend === data.nifty.trend && w.vix === data.nifty.vix_band);
  const today = new Date().toISOString().slice(0, 10);
  const horizon = new Date(Date.now() + 90 * 86400000).toISOString().slice(0, 10);
  const astro = (niftyDates.events as { date: string; name: string; up: number; days: number }[])
    .filter((e) => e.date >= today && e.date <= horizon && !OUTLOOK_EVENTS.some((o) => o.kind === "astro" && o.date === e.date))
    .map((e): OutlookEvent => ({ date: e.date, kind: "astro", title: `${e.name} (Astro Watch)`, note: `Nifty up ${e.up}% over the next ${e.days} trading days before` }));
  const events: OutlookEvent[] = [...OUTLOOK_EVENTS, ...astro].filter((e) => (e.end ?? e.date) >= today && e.date <= horizon).sort((a, b) => a.date.localeCompare(b.date));
  const nowMonth = new Date().getMonth() + 1;
  const nextMonths = [0, 1, 2].map((k) => ((nowMonth + k) % 12) + 1);
  const n = data?.nifty;

  return (
    <div className="page outlook-page">
      <PageHero
        tone="outlook"
        eyebrow="Outlook · the next week and month"
        title="Outlook"
        subtitle="Where Nifty, Gold and Silver are likely to stay, what the market's mood has meant before, and the dates that can move it — as probabilities, never as a call."
        motif={<BellCurveMotif />}
      >
        {n && <span className="hero-pill">Nifty {num(n.close, 2)} · India VIX {n.vix}</span>}
        <button type="button" className="hero-pill hero-pill-soft ol-refresh" onClick={refresh} disabled={loading}>
          {loading ? "Refreshing…" : data ? `Updated ${new Date(data.as_of).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" })} · refresh` : "Load"}
        </button>
      </PageHero>
      {error && <div className="error-banner">{error}</div>}

      {n && (
        <div className="ol-grid">
          <section className="card ol-card">
            <div className="dash-card-head">
              <div>
                <h2>Nifty range</h2>
                <p className="muted small">From India VIX {n.vix} — the market&apos;s own volatility forecast. Inner band ≈ 68%, outer ≈ 95%.</p>
              </div>
            </div>
            {(["week", "month"] as const).map((k) => {
              const r = n.ranges[k];
              const rec = record.vix_range[k];
              return (
                <div key={k} className="ol-range-block">
                  <div className="ol-range-head">
                    <b>Next {k === "week" ? "week (5 days)" : "month (21 days)"}</b>
                    <span className="muted small">±{num(r.move_1s)} pts · ±{r.move_pct_1s}%</span>
                  </div>
                  <RangeBar r={r} />
                  <p className="muted small ol-rec">
                    Record 2008–2026: Nifty ended inside the inner band {rec.inside_1sigma}% and inside the outer band {rec.inside_2sigma}% of the time.
                  </p>
                </div>
              );
            })}
          </section>

          <section className="card ol-card">
            <div className="dash-card-head">
              <div>
                <h2>Market weather</h2>
                <p className="muted small">Nifty against its 50- and 200-day averages, and the India VIX band</p>
              </div>
            </div>
            <div className="ol-weather">
              <span className={`ol-tag ${n.trend.startsWith("up") ? "ol-tag-up" : n.trend.startsWith("down") ? "ol-tag-down" : "ol-tag-mid"}`}>{n.trend}</span>
              <span className="ol-tag ol-tag-vix">VIX {n.vix} · {n.vix_band}</span>
            </div>
            <div className="ol-dma muted small">
              50-DMA {n.dma50 != null ? num(n.dma50) : "—"} · 200-DMA {n.dma200 != null ? num(n.dma200) : "—"} · close {num(n.close, 2)}
            </div>
            {weather ? (
              <div className="ol-weather-rec">
                <div className="ol-big">{weather.up20}%</div>
                <div>
                  <b>of the time Nifty was higher 20 trading days later</b>
                  <span className="muted small">
                    in this same weather ({num(weather.days)} days since 2008) · average {weather.avg20 > 0 ? "+" : ""}{weather.avg20}% · a bad case (worst 10%) {weather.worst20}%.
                    Any day: {record.weather_base.up20}% up, average +{record.weather_base.avg20}%.
                  </span>
                </div>
              </div>
            ) : (
              <p className="muted small">Too few past days in this exact weather to show a record.</p>
            )}
          </section>
        </div>
      )}

      {data && data.commodities.length > 0 && (
        <section className="card">
          <div className="dash-card-head">
            <div>
              <h2>Gold and Silver range</h2>
              <p className="muted small">MCX front-month futures, from the last 20 days&apos; volatility. Inner band ≈ 68%, outer ≈ 95%.</p>
            </div>
          </div>
          <div className="ol-grid">
            {data.commodities.map((c) => (
              <div key={c.symbol} className="ol-metal">
                <div className="ol-range-head">
                  <b>{c.name}</b>
                  <span className="muted small">{c.close != null ? `₹${num(c.close)} · volatility ${c.vol}% a year` : c.error}</span>
                </div>
                {c.ranges && (["week", "month"] as const).map((k) => (
                  <div key={k} className="ol-metal-row">
                    <span className="muted small">Next {k}</span>
                    <RangeBar r={c.ranges![k]} unit="₹" />
                  </div>
                ))}
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="card">
        <div className="dash-card-head">
          <div>
            <h2>Next 90 days: dates that can move the market</h2>
            <p className="muted small">Official dates (RBI, US Fed, Budget, NSE); results-season and some holiday dates are approximate until announced.</p>
          </div>
        </div>
        <div className="ol-events">
          {events.map((e) => {
            const d = new Date(`${e.date}T00:00:00`);
            return (
              <div key={`${e.date}-${e.title}`} className="ol-event">
                <div className="aw-day"><b>{d.getDate()}</b><span>{d.toLocaleDateString("en-IN", { month: "short" })}</span></div>
                <span className={`ol-kind ${KIND[e.kind].cls}`}>{KIND[e.kind].label}</span>
                <div className="ol-event-text">
                  <span className="ol-event-title">{e.title}{e.approx ? <em className="ol-approx">approx</em> : null}</span>
                  <span className="muted small">{e.end ? `${fmt(e.date)} – ${fmt(e.end)} · ` : ""}{e.note}</span>
                </div>
              </div>
            );
          })}
        </div>
        <div className="ol-budget">
          <b>Budget day record (1 Feb, 2017–2026)</b>
          <div className="ol-budget-row">
            {record.budget.map((b) => (
              <span key={b.year} className={`ol-bud ${b.day >= 0 ? "wk-up" : "wk-down"}`} title={`next 5 days ${b.next5}%`}>
                {b.year}<b>{b.day > 0 ? "+" : ""}{b.day}%</b>
              </span>
            ))}
          </div>
          <span className="muted small">An ordinary day moves about {record.normal_day_move}% either way; budget days have ranged from −2.1% to +4.7%.</span>
        </div>
      </section>

      <section className="card">
        <div className="dash-card-head">
          <div>
            <h2>The next three months, before</h2>
            <p className="muted small">How often each month ended higher (Nifty 2008–2025, Sensex 1998–2025)</p>
          </div>
        </div>
        <div className="tb-summary-grid wk-kpis">
          {nextMonths.map((m) => {
            const nf = (record.season_nifty as Season)[String(m)];
            const sx = (record.season_sensex as Season)[String(m)];
            return (
              <div key={m} className="tb-summary-tile">
                <div className="tb-summary-label">{MONTH[m].toUpperCase()}</div>
                <div className={`tb-summary-value ${nf.up >= 55 ? "wk-up" : nf.up < 45 ? "wk-down" : ""}`}>{nf.up}% up</div>
                <div className="tb-config-hint" style={{ margin: 0 }}>
                  Nifty avg {nf.avg > 0 ? "+" : ""}{nf.avg}% ({nf.years} yrs) · Sensex {sx.up}% up ({sx.years} yrs)
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <p className="muted small aw-foot">
        Live numbers: Angel One (Nifty, India VIX, MCX Gold and Silver). Records: Nifty, Sensex and India VIX daily closes
        since 2008 / 1997. Ranges and records describe probabilities, not certainties. For education only; not investment advice.
      </p>
    </div>
  );
}
