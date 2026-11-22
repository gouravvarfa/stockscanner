import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useChart } from "../chart/ChartContext";
import { HeatmapIcon } from "../components/icons";
import { useWeeklyReport } from "../context/WeeklyReportContext";
import { type SectorStock } from "../services/weeklySectorsApi";
import stockLogos from "../data/stockLogos.json";

/**
 * Heatmap (2026-11-22): every sector and its stocks in one coloured grid - green up, red down - for one day, one week
 * or one month. It is drawn from the Weekly Sectors report (the same run, shared through this device's saved report),
 * so nothing extra is fetched.
 */

// Company logos (TradingView's public logo images, ids looked up once for every stock in the sector lists).
const LOGOS = stockLogos as Record<string, string>;
function StockLogo({ symbol }: { symbol: string }) {
  // hidden until it has loaded (no empty white circle on a slow network); the slot keeps its place either way
  const [state, setState] = useState<"loading" | "ok" | "failed">("loading");
  const id = LOGOS[symbol];
  if (!id || state === "failed") return null;
  return (
    <img
      className={state === "ok" ? "hm-logo hm-logo-ok" : "hm-logo"}
      src={`https://s3-symbol-logo.tradingview.com/${id}.svg`}
      alt=""
      loading="lazy"
      decoding="async"
      onLoad={() => setState("ok")}
      onError={() => setState("failed")}
    />
  );
}

type Period = "r1d" | "r1w" | "r1m";
const PERIODS: { key: Period; label: string; steps: number[] }[] = [
  // colour steps (in %): beyond the last step = the deepest colour
  { key: "r1d", label: "1 Day", steps: [0.25, 1, 2, 3] },
  { key: "r1w", label: "1 Week", steps: [0.5, 2, 4, 6] },
  { key: "r1m", label: "1 Month", steps: [1, 4, 8, 12] },
];

function colourClass(v: number | null | undefined, steps: number[]): string {
  if (v === null || v === undefined) return "hm-na";
  const a = Math.abs(v);
  const level =
    a < steps[0]
      ? 0
      : a < steps[1]
        ? 1
        : a < steps[2]
          ? 2
          : a < steps[3]
            ? 3
            : 4;
  if (level === 0) return "hm-flat";
  return v > 0 ? `hm-up${level}` : `hm-dn${level}`;
}

function pct(v: number | null | undefined): string {
  return v === null || v === undefined
    ? "—"
    : `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function tone(v: number | null | undefined): string {
  return v === null || v === undefined ? "muted" : v >= 0 ? "wk-up" : "wk-down";
}

// The colour key: every band of the chosen period, labelled with where it starts (the middle one is "about zero").
function scaleOf(steps: number[]) {
  const [a, b, c, d] = steps;
  return [
    { cls: "hm-dn4", label: `-${d}`, title: `down ${d}% or more` },
    { cls: "hm-dn3", label: `-${c}`, title: `down ${c}% to ${d}%` },
    { cls: "hm-dn2", label: `-${b}`, title: `down ${b}% to ${c}%` },
    { cls: "hm-dn1", label: `-${a}`, title: `down ${a}% to ${b}%` },
    { cls: "hm-flat", label: "0", title: `between -${a}% and +${a}%` },
    { cls: "hm-up1", label: `+${a}`, title: `up ${a}% to ${b}%` },
    { cls: "hm-up2", label: `+${b}`, title: `up ${b}% to ${c}%` },
    { cls: "hm-up3", label: `+${c}`, title: `up ${c}% to ${d}%` },
    { cls: "hm-up4", label: `+${d}`, title: `up ${d}% or more` },
  ];
}

type WatchRow = { st: SectorStock; sectors: string[] };

// One box of "Stocks to watch", in the Weekly Sectors action-list style: a coloured top line, title, count, short note
// and one row per stock (logo, symbol, sectors, 1-week change). A row opens the stock's chart.
function WatchBox({ tone: boxTone, title, note, rows, empty, onPick }: {
  tone: "watch" | "near";
  title: string;
  note: string;
  rows: WatchRow[];
  empty: string;
  onPick: (st: SectorStock, sector: string) => void;
}) {
  return (
    <div className={`act-box act-${boxTone}`}>
      <div className="act-head">
        <span className="act-name">{title}</span>
        <span className="act-count">{rows.length}</span>
      </div>
      <p className="act-note">{note}</p>
      {rows.length === 0 ? (
        <p className="act-empty">{empty}</p>
      ) : (
        <ul className="act-items hm-watch-items">
          {rows.map(({ st, sectors }) => (
            <li key={st.symbol}>
              <button
                type="button"
                className="hm-watch-row"
                onClick={() => onPick(st, sectors[0])}
                title={`${st.name ?? st.symbol}: open chart`}
              >
                <span className="hm-watch-logo">
                  <StockLogo symbol={st.symbol} />
                </span>
                <span className="act-main">{st.symbol}</span>
                <span className="act-sub">{sectors.join(", ")}</span>
                <span className={`act-val ${tone(st.r1w)}`}>
                  {pct(st.r1w)}
                  <small>1W</small>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function HeatmapPage() {
  // The same report run as Weekly Sectors (app level): it keeps going while another page is open.
  const { report, job, running, error, run } = useWeeklyReport();
  const [period, setPeriod] = useState<Period>(() =>
    report?.benchmark.r1d !== undefined ? "r1d" : "r1w",
  );
  const [strongOnly, setStrongOnly] = useState(false);
  const { openChart } = useChart();
  const hasDay = report?.benchmark.r1d !== undefined;
  const conf = PERIODS.find((p) => p.key === period) ?? PERIODS[1];

  // STRONG sectors always on top (2026-11-22, by the chosen period's return), then every other sector
  const groups = useMemo(() => {
    if (!report) return [];
    const val = (v: number | null | undefined) =>
      v === null || v === undefined ? -Infinity : v;
    const byReturn = (list: typeof report.sectors) =>
      [...list].sort((a, b) => val(b[period]) - val(a[period]));
    const strong = byReturn(
      report.sectors.filter((s) => s.verdict === "STRONG"),
    );
    const others = strongOnly
      ? []
      : byReturn(report.sectors.filter((s) => s.verdict !== "STRONG"));
    return [
      {
        title: "STRONG sectors",
        note: "daily, weekly and monthly RSI of the sector index all above 60",
        list: strong,
      },
      { title: "Other sectors", note: "", list: others },
    ].filter((g) => g.list.length > 0);
  }, [report, period, strongOnly]);

  // The stocks to look at first (2026-11-22: boxes at the bottom of the page in the Weekly action-list style, ★ in
  // the grid): the leaders of the STRONG sectors (beat their own sector over 1W and 1M, above the 50-day average) and
  // the week's new 52-week highs. One row per stock, with every sector it qualified in.
  const watch = useMemo(() => {
    if (!report) return { leaders: [] as WatchRow[], highs: [] as WatchRow[] };
    const collect = (
      hits: { st: SectorStock; sector: string }[],
      key: (st: SectorStock) => number,
      n: number,
    ) => {
      const rows = new Map<string, WatchRow>();
      for (const { st, sector } of hits) {
        const row = rows.get(st.symbol);
        if (!row) rows.set(st.symbol, { st, sectors: [sector] });
        else {
          if (!row.sectors.includes(sector)) row.sectors.push(sector);
          if (key(st) > key(row.st)) row.st = st;
        }
      }
      return [...rows.values()]
        .sort((a, b) => key(b.st) - key(a.st))
        .slice(0, n);
    };
    const leaders = collect(
      report.sectors
        .filter((s) => s.verdict === "STRONG")
        .flatMap((s) =>
          s.stocks
            .filter((st) => st.signal === "Leader" && st.above_50dma !== false)
            .map((st) => ({ st, sector: s.label })),
        ),
      (st) => st.combined,
      10,
    );
    const highs = collect(
      report.sectors.flatMap((s) =>
        s.stocks
          .filter((st) => st.high_52w)
          .map((st) => ({ st, sector: s.label })),
      ),
      (st) => st.r1w,
      12,
    );
    return { leaders, highs };
  }, [report]);
  const watchSet = useMemo(
    () =>
      new Set(
        [...watch.leaders, ...watch.highs].map((w) => w.st.symbol),
      ),
    [watch],
  );

  const showChart = (st: SectorStock, sector: string) =>
    openChart(st.symbol, {
      strategy: `Heatmap · ${sector}`,
      daily_rsi: st.rsi_d ?? null,
      weekly_rsi: null,
      monthly_rsi: null,
      signal_date: report?.end_date ?? null,
      explanation: `${st.symbol}: ${pct(st.r1d)} 1D, ${pct(st.r1w)} 1W, ${pct(st.r1m)} 1M.`,
      indicators: { rsi: true, volume: true, bollinger: true },
    });

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Heatmap</h1>
          <p className="page-subtitle">
            Every sector and its stocks in one view: green is up, red is down.
            Click a stock for its chart.
          </p>
        </div>
      </div>

      <div className="card hm-controls">
        <div className="hm-seg" role="tablist" aria-label="Period">
          {PERIODS.map((p) => (
            <button
              key={p.key}
              type="button"
              role="tab"
              aria-selected={period === p.key}
              className={period === p.key ? "active" : ""}
              disabled={p.key === "r1d" && !!report && !hasDay}
              title={
                p.key === "r1d" && !!report && !hasDay
                  ? "This report was made before 1 Day was added - press Refresh"
                  : undefined
              }
              onClick={() => setPeriod(p.key)}
            >
              {p.label}
            </button>
          ))}
        </div>
        <label className="hm-check">
          <input
            type="checkbox"
            checked={strongOnly}
            onChange={(e) => setStrongOnly(e.target.checked)}
          />{" "}
          Strong sectors only
        </label>
        <button
          className="primary-button"
          onClick={() => void run()}
          disabled={running}
        >
          {running ? "Running…" : report ? "Refresh" : "Run Report"}
        </button>
        <span className="tb-config-hint" style={{ margin: 0 }}>
          {running
            ? `${job?.phase} · ${job?.done}/${job?.total}`
            : report
              ? `Week ending ${new Date(report.end_date ?? report.as_of).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" })} · from the Weekly Sectors report`
              : "Uses the Weekly Sectors report: press Run Report (a few minutes)."}
        </span>
      </div>

      {report && !hasDay && !running && (
        <div className="notice-banner">
          This report was made before the update, so <b>1 Day</b> and the{" "}
          <b>52-week highs</b> are not in it yet. Press <b>Refresh</b>
          once (a few minutes) and they appear.
        </div>
      )}

      {error && <div className="error-banner">{error}</div>}

      {!report && !running && (
        <div className="card state-block">
          <div className="state-icon">
            <HeatmapIcon width={28} height={28} />
          </div>
          <div className="state-title">No report yet</div>
          <div className="state-subtitle">
            Press Run Report here, or run it on{" "}
            <Link to="/weekly-sectors">Weekly Sectors</Link> - both pages share
            it.
          </div>
        </div>
      )}

      {report && (
        <>
          <div className="hm-legend">
            <div
              className="hm-scale"
              role="img"
              aria-label={`Colour key, % change over ${conf.label}: red is down, green is up`}
            >
              <span className="hm-scale-end">Down</span>
              {scaleOf(conf.steps).map((b) => (
                <span key={b.cls} className={`hm-scale-band ${b.cls}`} title={b.title}>
                  {b.label}
                </span>
              ))}
              <span className="hm-scale-end">Up</span>
            </div>
            <span className="hm-legend-note">% change, {conf.label}</span>
            <span className="hm-legend-note">
              <span className="hm-star hm-star-inline" aria-hidden="true">★</span>
              stock to watch, listed at the bottom
            </span>
            <span className="hm-legend-note">
              Nifty 50{" "}
              <b className={tone(report.benchmark[period])}>
                {pct(report.benchmark[period] ?? null)}
              </b>
            </span>
          </div>

          {groups.length === 0 && (
            <p className="muted">No STRONG sector in this report.</p>
          )}

          {groups.map((g) => (
            <div key={g.title} className="hm-group">
              <div className="hm-group-head">
                <h2>{g.title}</h2>
                {g.note && <span className="muted small">{g.note}</span>}
              </div>
              <div className="hm-sectors">
                {g.list.map((s) => (
                  <section key={s.key} className="card hm-sector">
                    <header className="hm-sector-head">
                      <span className="hm-sector-name">{s.label}</span>
                      <span
                        className={`hm-sector-ret ${colourClass(s[period], conf.steps)}`}
                      >
                        {pct(s[period])}
                      </span>
                      {s.verdict !== "N/A" && (
                        <span
                          className={`wk-chip wk-ver-${s.verdict.toLowerCase()}`}
                        >
                          {s.verdict}
                        </span>
                      )}
                    </header>
                    <div className="hm-grid">
                      {[...s.stocks]
                        .sort(
                          (a, b) =>
                            (b[period] ?? -Infinity) - (a[period] ?? -Infinity),
                        )
                        .map((st) => (
                          <button
                            key={st.symbol}
                            type="button"
                            className={`hm-tile ${colourClass(st[period], conf.steps)}${watchSet.has(st.symbol) ? " hm-tile-focus" : ""}`}
                            onClick={() => showChart(st, s.label)}
                            title={`${st.name ?? st.symbol}${watchSet.has(st.symbol) ? " (stock to watch)" : ""}\n1D ${pct(st.r1d)} · 1W ${pct(st.r1w)} · 1M ${pct(st.r1m)}`}
                          >
                            {watchSet.has(st.symbol) && (
                              <span className="hm-star" aria-label="stock to watch">★</span>
                            )}
                            <span className="hm-logo-slot">
                              <StockLogo symbol={st.symbol} />
                            </span>
                            <span className="hm-sym">{st.symbol}</span>
                            <span className="hm-val">{pct(st[period])}</span>
                          </button>
                        ))}
                    </div>
                  </section>
                ))}
              </div>
            </div>
          ))}

          {/* Stocks to watch: always the last thing on the page (user, 2026-11-22), boxes like the Weekly action list */}
          <section className="card hm-watch" aria-labelledby="hm-watch-title">
            <div className="act-top">
              <h2 id="hm-watch-title" style={{ margin: 0 }}>
                Stocks to watch
              </h2>
              <span className="muted small">
                Week ending{" "}
                {new Date(report.end_date ?? report.as_of).toLocaleDateString(
                  "en-IN",
                  { day: "2-digit", month: "short", year: "numeric" },
                )}{" "}
                · marked ★ in the grid above
              </span>
            </div>
            <div className="act-grid hm-watch-grid">
              <WatchBox
                tone="watch"
                title="Sector leaders"
                note="Beat their STRONG sector over 1 week and 1 month, above the 50-day average"
                rows={watch.leaders}
                empty="None this week"
                onPick={showChart}
              />
              <WatchBox
                tone="near"
                title="New 52-week highs"
                note="Made a new 52-week high this week, in any sector"
                rows={watch.highs}
                empty={
                  hasDay ? "None this week" : "Press Refresh once to see these"
                }
                onPick={showChart}
              />
            </div>
          </section>
        </>
      )}
    </div>
  );
}
