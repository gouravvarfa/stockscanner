import data from "../data/astroWatch.json";

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

export function AstroWatchPage() {
  const today = new Date().toISOString().slice(0, 10);
  const upcoming = events.filter((e) => e.date >= today);
  const past = events.filter((e) => e.gold !== undefined).reverse();
  const next = upcoming[0];
  const daysLeft = next ? Math.ceil((new Date(`${next.date}T00:00:00`).getTime() - Date.now()) / 86400000) : null;

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Astro Watch</h1>
          <p className="page-subtitle">
            Shukra–Mangal yuti (Venus–Mars conjunction): a warning that Gold, Silver and Crude may move more than usual
            in the next 5 trading days. It never says up or down.
          </p>
        </div>
      </div>

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
    </div>
  );
}
