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

  // The stocks to look at first: leaders of the STRONG sectors (beat their own sector over 1W and 1M, above the 50-day
  // average) and the new 52-week highs of the week.
  const focus = useMemo(() => {
    const pick = (
      rows: { st: SectorStock; sector: string }[],
      key: (x: { st: SectorStock }) => number,
      n: number,
    ) => {
      const best = new Map<string, { st: SectorStock; sector: string }>();
      for (const r of rows)
        if (!best.has(r.st.symbol) || key(r) > key(best.get(r.st.symbol)!))
          best.set(r.st.symbol, r);
      return [...best.values()].sort((a, b) => key(b) - key(a)).slice(0, n);
    };
    if (!report) return { leaders: [], highs: [] };
    const leaders = pick(
      report.sectors
        .filter((s) => s.verdict === "STRONG")
        .flatMap((s) =>
          s.stocks
            .filter((st) => st.signal === "Leader" && st.above_50dma !== false)
            .map((st) => ({ st, sector: s.label })),
        ),
      (x) => x.st.combined,
      10,
    );
    const highs = pick(
      report.sectors.flatMap((s) =>
        s.stocks
          .filter((st) => st.high_52w)
          .map((st) => ({ st, sector: s.label })),
      ),
      (x) => x.st.r1w,
      12,
    );
    return { leaders, highs };
  }, [report]);
  const focusSet = useMemo(
    () => new Set([...focus.leaders, ...focus.highs].map((x) => x.st.symbol)),
    [focus],
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
          <div className="card hm-focus-card">
            <h2 style={{ marginTop: 0 }}>Focus: stocks to watch</h2>
            <div className="hm-focus-row">
              <span className="hm-focus-title">Leaders in STRONG sectors</span>
              <div className="hm-focus-list">
                {focus.leaders.length === 0 ? (
                  <span className="muted small">none this week</span>
                ) : (
                  focus.leaders.map(({ st, sector }) => (
                    <button
                      key={st.symbol}
                      type="button"
                      className="hm-focus-chip"
                      onClick={() => showChart(st, sector)}
                      title={st.name ?? st.symbol}
                    >
                      <b>{st.symbol}</b>
                      <span className="muted">{sector}</span>
                      <span className="wk-up">{pct(st.r1w)} 1W</span>
                    </button>
                  ))
                )}
              </div>
            </div>
            <div className="hm-focus-row">
              <span className="hm-focus-title">New 52-week high this week</span>
              <div className="hm-focus-list">
                {focus.highs.length === 0 ? (
                  <span className="muted small">
                    {report.benchmark.r1d === undefined
                      ? "run the report again to see these"
                      : "none this week"}
                  </span>
                ) : (
                  focus.highs.map(({ st, sector }) => (
                    <button
                      key={st.symbol}
                      type="button"
                      className="hm-focus-chip"
                      onClick={() => showChart(st, sector)}
                      title={st.name ?? st.symbol}
                    >
                      <b>{st.symbol}</b>
                      <span className="muted">{sector}</span>
                      <span className={st.r1w >= 0 ? "wk-up" : "wk-down"}>
                        {pct(st.r1w)} 1W
                      </span>
                    </button>
                  ))
                )}
              </div>
            </div>
            <p className="muted small" style={{ margin: "8px 0 0" }}>
              Leader = beat its own sector over 1 week and 1 month and trades
              above its 50-day average. ★ marks these stocks in the grid below.
              Click any stock for its chart.
            </p>
          </div>

          <div className="hm-legend">
            <span className="muted small">Down</span>
            {[4, 3, 2, 1].map((l) => (
              <i key={`d${l}`} className={`hm-dn${l}`} />
            ))}
            <i className="hm-flat" />
            {[1, 2, 3, 4].map((l) => (
              <i key={`u${l}`} className={`hm-up${l}`} />
            ))}
            <span className="muted small">Up</span>
            <span className="muted small hm-legend-note">
              steps of {conf.steps.join(" / ")}% · Nifty 50{" "}
              {pct(report.benchmark[period] ?? null)}
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
                            className={`hm-tile ${colourClass(st[period], conf.steps)}${focusSet.has(st.symbol) ? " hm-tile-focus" : ""}`}
                            onClick={() => showChart(st, s.label)}
                            title={`${st.name ?? st.symbol}\n1D ${pct(st.r1d)} · 1W ${pct(st.r1w)} · 1M ${pct(st.r1m)}`}
                          >
                            {focusSet.has(st.symbol) && (
                              <span className="hm-star" aria-label="focus">★</span>
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
        </>
      )}
    </div>
  );
}
