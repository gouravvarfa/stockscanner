import { useState } from "react";
import { AnniversaryMotif, PageHero } from "../components/PageHero";
import data from "../data/anniversaries.json";

/**
 * Anniversary Dates (2026-11-23): the coming dates (same day and month) of past big tops and bottoms in Nifty and
 * Gold, each with the full history of that calendar date: price, the day's move, the next 5 / 20 days, whether a
 * top or bottom formed near it, big moves and well-known events. History and context only: tested, these dates do
 * not mark turns more often than any other date.
 */

type Turn = { kind: "top" | "bottom"; strength: number; days_off: number } | null;
type Row = { year: number; date: string; close: number; day: number; next5: number | null; next20: number | null; turn: Turn; event: string | null; big: boolean };
type Source = { year: number; kind: "top" | "bottom"; price: number; strength: number };
type Anniv = { md: string; next: string; sources: Source[]; history: Row[] };
type Market = { name: string; from: string; dates: Anniv[] };
const MARKETS = data.markets as Record<"nifty" | "gold", Market>;
const RECORD = data.record as Record<"nifty" | "gold", { anniv3: number; random3: number; anniv5: number; random5: number }>;

const num = (v: number, d = 0) => v.toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d });
const pct = (v: number | null) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(1)}%`);
const tone = (v: number | null) => (v == null ? "muted" : v >= 0 ? "wk-up" : "wk-down");
const inDays = (iso: string) => Math.ceil((new Date(`${iso}T00:00:00`).getTime() - Date.now()) / 86400000);
const STRENGTH: Record<number, string> = { 30: "swing", 60: "big", 125: "major" };

function DateCard({ a, unit }: { a: Anniv; unit: string }) {
  const d = new Date(`${a.next}T00:00:00`);
  const events = a.history.filter((h) => h.event);
  const turns = a.history.filter((h) => h.turn);
  return (
    <details className="an-card">
      <summary>
        <div className="aw-day"><b>{d.getDate()}</b><span>{d.toLocaleDateString("en-IN", { month: "short" })}</span></div>
        <div className="an-sum">
          <div className="an-sources">
            {a.sources.map((s) => (
              <span key={`${s.year}-${s.kind}`} className={`an-src an-${s.kind}`}>
                {s.year} {s.kind} {unit}{num(s.price)}
              </span>
            ))}
          </div>
          <span className="muted small">
            in {inDays(a.next)} days · {turns.length} of {a.history.length} years had a top or bottom within ±3 days
            {events.length ? ` · ${events.length} known event${events.length > 1 ? "s" : ""}` : ""}
          </span>
        </div>
        <span className="an-open">History</span>
      </summary>
      <div className="table-wrap">
        <table className="dash-signal-table an-table">
          <thead>
            <tr>
              <th>Year</th>
              <th className="num-cell">Close</th>
              <th className="num-cell">That day</th>
              <th className="num-cell">Next 5 days</th>
              <th className="num-cell">Next 20 days</th>
              <th>What happened</th>
            </tr>
          </thead>
          <tbody>
            {[...a.history].reverse().map((h) => (
              <tr key={h.year} className={h.event || h.turn?.days_off === 0 ? "an-hl" : ""}>
                <td><span className="dash-two">{h.year}<small>{new Date(`${h.date}T00:00:00`).toLocaleDateString("en-IN", { day: "2-digit", month: "short", weekday: "short" })}</small></span></td>
                <td className="num-cell">{unit}{num(h.close, unit ? 0 : 1)}</td>
                <td className={`num-cell ${tone(h.day)}`}>{pct(h.day)}</td>
                <td className={`num-cell ${tone(h.next5)}`}>{pct(h.next5)}</td>
                <td className={`num-cell ${tone(h.next20)}`}>{pct(h.next20)}</td>
                <td className="an-what-cell">
                  <div className="an-what">
                  {h.turn && (
                    <span className={`an-src an-${h.turn.kind}`}>
                      {STRENGTH[h.turn.strength]} {h.turn.kind}{h.turn.days_off ? ` ${h.turn.days_off}d away` : " that day"}
                    </span>
                  )}
                  {h.big && <span className="an-big">{h.day < 0 ? "big fall" : "big rise"}</span>}
                  {h.event && <span className="an-event">{h.event}</span>}
                  {!h.turn && !h.big && !h.event && <span className="muted small">—</span>}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

export function AnniversaryPage() {
  const [mk, setMk] = useState<"nifty" | "gold">("nifty");
  const m = MARKETS[mk];
  const today = new Date().toISOString().slice(0, 10);
  const horizon = new Date(Date.now() + 90 * 86400000).toISOString().slice(0, 10);
  const list = m.dates.filter((a) => a.next >= today && a.next <= horizon);
  const unit = mk === "gold" ? "$" : "";
  const rec = RECORD[mk];
  return (
    <div className="page anniv-page">
      <PageHero
        tone="anniv"
        eyebrow="History · the same date in past years"
        title="Anniversary Dates"
        subtitle="The coming dates when Nifty or Gold made a big top or bottom in an earlier year — and everything that happened on that date before: the move, what followed, crashes and events."
        motif={<AnniversaryMotif />}
      >
        <span className="hero-pill">Next 90 days · {list.length} dates</span>
        <span className="hero-pill hero-pill-soft">Context only — not a turn signal</span>
      </PageHero>

      <div className="aw-seg an-seg" role="tablist" aria-label="Market">
        <button type="button" role="tab" aria-selected={mk === "nifty"} className={mk === "nifty" ? "active" : ""} onClick={() => setMk("nifty")}>Nifty 50</button>
        <button type="button" role="tab" aria-selected={mk === "gold"} className={mk === "gold" ? "active" : ""} onClick={() => setMk("gold")}>Gold</button>
      </div>

      <section className="card">
        <div className="dash-card-head">
          <div>
            <h2>{m.name}: upcoming anniversaries</h2>
            <p className="muted small">
              A date is listed when a big top or bottom (the highest or lowest point of ±60 trading days) fell on it in an
              earlier year. Open a date for its full history since {m.from}.
            </p>
          </div>
        </div>
        <div className="an-list">
          {list.length === 0 ? <p className="muted dash-empty">No anniversary in the next 90 days.</p> : list.map((a) => <DateCard key={a.md} a={a} unit={unit} />)}
        </div>
        <p className="muted small aw-honest">
          Tested on {m.name}: a real turn came within ±3 trading days of an anniversary {rec.anniv3}% of the time against{" "}
          {rec.random3}% for random dates (±5 days: {rec.anniv5}% vs {rec.random5}%). Anniversaries are so frequent that one
          is always near any turn — read these dates as history and context, never as a signal.
        </p>
      </section>

      <p className="muted small aw-foot">
        Prices: Nifty 50 and COMEX Gold daily closes (data to {new Date(`${data.data_to}T00:00:00`).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" })}). Events
        are well-known market days; a "big fall/rise" is a day move of 3% or more. For education only; not investment advice.
      </p>
    </div>
  );
}
