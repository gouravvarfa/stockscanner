import type React from "react";
import { SectorLogo } from "../components/SectorIcon";
import { useEffect, useRef, useState } from "react";
import { useChart } from "../chart/ChartContext";
import { TrendIcon } from "../components/icons";
import { StockLogo } from "../components/StockLogo";
import { useWeeklyReport } from "../context/WeeklyReportContext";
import {
  downloadWeeklyPdf,
  downloadWeeklyXlsx,
  type SectorRow,
  type SectorStock,
  type WeeklyReport,
} from "../services/weeklySectorsApi";

function pct(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}
function pp(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(2)}`;
}
function tone(v: number | null | undefined): string {
  return v === null || v === undefined ? "" : v > 0 ? "wk-up" : v < 0 ? "wk-down" : "";
}
function niceDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}
// Charts opened from this page show every study: RSI, volume and Bollinger Bands (Daily / Weekly / Monthly are the
// chart's own timeframe buttons).
const ALL_INDICATORS = { rsi: true, volume: true, bollinger: true } as const;

function ChartButton({ label, onOpen }: { label: string; onOpen: () => void }) {
  return (
    <button
      type="button"
      className="wk-chart-btn"
      onClick={(e) => {
        e.stopPropagation(); // the scorecard row itself selects the sector
        onOpen();
      }}
      title={`Open the ${label} chart`}
      aria-label={`Open the ${label} chart`}
    >
      <TrendIcon width={13} height={13} aria-hidden="true" />
      Chart
    </button>
  );
}

const signalClass = (s: string) => `wk-chip wk-sig-${s.replace(/\s+/g, "-").replace("/", "").toLowerCase()}`;
const verdictClass = (v: string) => `wk-chip wk-ver-${v.replace("/", "").toLowerCase()}`;
const BUCKETS: [keyof WeeklyReport["buckets"], string, string, string][] = [
  ["strength_leaders", "Strength leaders", "Leaders in strong sectors", "wk-b-green"],
  ["watch", "Watch", "Near-leaders and pullbacks in strong sectors", "wk-b-blue"],
  ["stock_specific", "Stock-specific", "Leaders outside the strong sectors", "wk-b-amber"],
  ["relative_weakness", "Relative weakness", "Laggards and bounce-only in strong sectors", "wk-b-red"],
];

/** Short plain-language findings, the same ones the PDF opens with. */
function insights(r: WeeklyReport): string[] {
  const out: string[] = [];
  const strong = r.summary.strong_sectors;
  out.push(
    strong.length
      ? `${strong.join(", ")} ${strong.length > 1 ? "are" : "is"} STRONG: daily, weekly and monthly RSI all above 60.`
      : "No sector has its daily, weekly and monthly RSI all above 60 this week.",
  );
  const ranked = r.sectors.filter((s) => s.rank_1w && s.rank_1m);
  if (ranked.length) {
    const avg = (s: SectorRow) => ((s.rank_1w ?? 99) + (s.rank_1m ?? 99)) / 2;
    const top = [...ranked].sort((a, b) => avg(a) - avg(b))[0];
    const last = [...ranked].sort((a, b) => avg(b) - avg(a))[0];
    out.push(`${top.label} is moving the most: ${pct(top.r1w)} on the week (#${top.rank_1w}) and ${pct(top.r1m)} on the month (#${top.rank_1m}).`);
    out.push(`${last.label} is the weakest: ${pct(last.r1w)} on the week and ${pct(last.r1m)} on the month.`);
  }
  const [a, b] = r.top_movers;
  if (a) out.push(`${a.symbol} beats ${a.sector} by ${pp(a.vs1w)}pp (1W) and ${pp(a.vs1m)}pp (1M)${b ? `; ${b.symbol} beats ${b.sector} by ${pp(b.vs1w)}pp and ${pp(b.vs1m)}pp` : ""}.`);
  out.push(`${r.summary.leaders} of ${r.summary.rows} stock rows beat their sector on both 1W and 1M; ${r.summary.laggards} trail it on both.`);
  return out;
}


/** The week in four plain lines (2026-11-22): what to watch, what is about to turn STRONG, who beats the market,
 *  who is getting weaker. Everything comes from the report already on screen. */
function ActionCard({ report, onStock, onSector }: {
  report: WeeklyReport;
  onStock: (st: SectorStock, sector: string) => void;
  onSector: (key: string) => void;
}) {
  const b = report.benchmark;
  const rsiMin = (s: SectorRow) => Math.min(s.rsi.d ?? 0, s.rsi.w ?? 0, s.rsi.m ?? 0);
  const ahead = (s: SectorRow) =>
    b.r1w !== null && b.r1m !== null && s.r1w !== null && s.r1m !== null && s.r1w > b.r1w && s.r1m > b.r1m;
  const weeksAhead = (s: SectorRow) => (s.trail ?? []).filter((t) => t.rel_1w > 0 && t.rel_1m > 0).length;
  const strong = report.sectors.filter((s) => s.verdict === "STRONG");
  const watch = strong.map((s) => ({
    s,
    leaders: s.stocks.filter((st) => st.signal === "Leader" && st.above_50dma !== false).sort((x, y) => y.combined - x.combined).slice(0, 3),
  }));
  const near = report.sectors.filter((s) => s.verdict !== "STRONG" && !s.equal_weight && s.rsi.d !== null && rsiMin(s) >= 55);
  const outperf = report.sectors
    .filter(ahead)
    .sort((x, y) => (y.r1w! - b.r1w! + y.r1m! - b.r1m!) - (x.r1w! - b.r1w! + x.r1m! - b.r1m!));
  const weak = report.sectors.filter(
    (s) =>
      (s.prev?.verdict === "STRONG" && s.verdict !== "STRONG") ||
      (b.r1w !== null && b.r1m !== null && s.r1w !== null && s.r1m !== null && s.r1w < b.r1w && s.r1m < b.r1m && s.rsi.d !== null && s.rsi.d < 50),
  );
  // each stock once, with every STRONG sector it leads
  const watchMap = new Map<string, { st: SectorStock; sectors: string[] }>();
  for (const { s, leaders } of watch)
    for (const st of leaders) {
      const cur = watchMap.get(st.symbol);
      if (cur) cur.sectors.push(s.label);
      else watchMap.set(st.symbol, { st, sectors: [s.label] });
    }
  const watchList = [...watchMap.values()].sort((x, y) => y.st.combined - x.st.combined);
  const vsNifty = (s: SectorRow) =>
    b.r1w !== null && b.r1m !== null && s.r1w !== null && s.r1m !== null ? `${pp(s.r1w - b.r1w)} / ${pp(s.r1m - b.r1m)}` : "";
  const Box = ({ tone, title, note, count, logos, children }: { tone: string; title: string; note: string; count: number; logos?: boolean; children: React.ReactNode }) => (
    <div className={`act-box act-${tone}`}>
      <div className="act-head">
        <span className="act-name">{title}</span>
        <span className="act-count">{count}</span>
      </div>
      <p className="act-note">{note}</p>
      {count === 0 ? <p className="act-empty">None this week</p> : <ul className={logos ? "act-items act-items-logo" : "act-items"}>{children}</ul>}
    </div>
  );
  return (
    <div className="card">
      <div className="act-top">
        <h2 style={{ margin: 0 }}>This week&apos;s action list</h2>
        <span className="muted small">Week ending {niceDate(report.end_date)} · vs Nifty 50 {pct(b.r1w)} 1W, {pct(b.r1m)} 1M</span>
      </div>
      <div className="act-grid">
        <Box tone="watch" title="Watch" count={watchList.length} logos note="Leaders of the STRONG sectors, above their 50-day average">
          {watchList.map(({ st, sectors }) => (
            <li key={st.symbol} onClick={() => onStock(st, sectors[0])} title="Open chart">
              <span className="act-logo">
                <StockLogo symbol={st.symbol} />
              </span>
              <span className="act-main">{st.symbol}</span>
              <span className="act-sub">{sectors.join(", ")}</span>
              <span className="act-val wk-up">{pct(st.r1w)}</span>
            </li>
          ))}
        </Box>
        <Box tone="near" title="Near STRONG" count={near.length} note="All three RSI at 55 or more, not yet all above 60">
          {near.map((s) => (
            <li key={s.key} onClick={() => onSector(s.key)}>
              <span className="act-main">{s.label}</span>
              <span className="act-sub">RSI D/W/M</span>
              <span className="act-val">{s.rsi.d?.toFixed(0)}/{s.rsi.w?.toFixed(0)}/{s.rsi.m?.toFixed(0)}</span>
            </li>
          ))}
        </Box>
        <Box tone="out" title="Outperforming" count={outperf.length} note="Ahead of the Nifty 50 on the week and the month (pp)">
          {outperf.map((s) => (
            <li key={s.key} onClick={() => onSector(s.key)}>
              <span className="act-main">{s.label}</span>
              <span className="act-sub">{weeksAhead(s) ? `${weeksAhead(s)} of last 5 weeks` : ""}</span>
              <span className="act-val wk-up">{vsNifty(s)}</span>
            </li>
          ))}
        </Box>
        <Box tone="weak" title="Weakening" count={weak.length} note="No longer STRONG, or behind the Nifty 50 with daily RSI below 50">
          {weak.map((s) => (
            <li key={s.key} onClick={() => onSector(s.key)}>
              <span className="act-main">{s.label}</span>
              <span className="act-sub">{s.prev?.verdict === "STRONG" && s.verdict !== "STRONG" ? "no longer STRONG" : `RSI D ${s.rsi.d?.toFixed(0)}`}</span>
              <span className="act-val wk-down">{vsNifty(s)}</span>
            </li>
          ))}
        </Box>
      </div>
    </div>
  );
}

function RankPanel({ title, sectors, field }: { title: string; sectors: SectorRow[]; field: "r1w" | "r1m" }) {
  const rows = sectors.filter((s) => s[field] !== null).sort((a, b) => (b[field] ?? 0) - (a[field] ?? 0));
  const max = Math.max(...rows.map((s) => Math.abs(s[field] ?? 0)), 1);
  return (
    <div className="card wk-rank">
      <h3>{title}</h3>
      {rows.map((s, i) => {
        const v = s[field] ?? 0;
        const tier = i < 3 ? "wk-bar-green" : i >= rows.length - 2 ? "wk-bar-amber" : "wk-bar-blue";
        return (
          <div key={s.key} className="wk-rank-row">
            <span className="wk-rank-n">{i + 1}</span>
            <span className="wk-rank-label">{s.label}</span>
            <span className={`wk-rank-v ${tone(v)}`}>{pct(v)}</span>
            <span className="wk-bar-track">
              <span className={`wk-bar ${tier} ${v < 0 ? "wk-bar-neg" : ""}`} style={{ width: `${(Math.abs(v) / max) * 100}%` }} />
            </span>
          </div>
        );
      })}
    </div>
  );
}

function StockTable({ rows, withSector, sectorLabel, endDate }: {
  rows: SectorStock[];
  withSector?: boolean;
  sectorLabel?: string;
  endDate?: string | null;
}) {
  const { openChart } = useChart();
  // The same chart drawer every scanner page uses; the header shows how the stock did against its sector.
  const showChart = (s: SectorStock) =>
    openChart(s.symbol, {
      strategy: "Weekly Sectors",
      daily_rsi: null,
      weekly_rsi: null,
      monthly_rsi: null,
      signal_date: endDate ?? null,
      explanation:
        `${s.symbol}: ${pct(s.r1w)} on the week, ${pct(s.r1m)} on the month; ` +
        `${pp(s.vs1w)}pp (1W) and ${pp(s.vs1m)}pp (1M) vs ${s.sector ?? sectorLabel ?? "its sector"} - ${s.signal}.`,
      indicators: ALL_INDICATORS,
    });
  return (
    <div className="table-wrap">
      <table className="wk-table">
        <thead>
          <tr>
            <th>Stock</th>
            {withSector && <th>Sector</th>}
            <th>1W %</th>
            <th>1M %</th>
            <th>vs 1W</th>
            <th>vs 1M</th>
            <th>Signal</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((s) => (
            <tr key={`${s.symbol}-${s.sector ?? ""}`}>
              <td className="wk-sym" title={s.name ?? undefined}>
                <div className="wk-sym-cell">
                  <div className="wk-sym-id">
                    <span className="wk-logo">
                      <StockLogo symbol={s.symbol} />
                    </span>
                    <div className="wk-sym-text">
                      {s.symbol}
                      {s.name && <span className="wk-name">{s.name}</span>}
                    </div>
                  </div>
                  <ChartButton label={s.symbol} onOpen={() => showChart(s)} />
                </div>
              </td>
              {withSector && <td className="muted">{s.sector}</td>}
              <td className={tone(s.r1w)}>{pct(s.r1w)}</td>
              <td className={tone(s.r1m)}>{pct(s.r1m)}</td>
              <td className={`wk-vs ${s.vs1w > 0 ? "wk-vs-up" : "wk-vs-down"}`}>{pp(s.vs1w)}</td>
              <td className={`wk-vs ${s.vs1m > 0 ? "wk-vs-up" : "wk-vs-down"}`}>{pp(s.vs1m)}</td>
              <td>
                <span className={signalClass(s.signal)}>{s.signal}</span>
                {s.group && <span className="wk-group">{s.group}</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function WeeklySectorsPage() {
  // The run lives at app level (context/WeeklyReportContext): it keeps going while another page is open.
  const { report, job, running, error: runError, run: runReport } = useWeeklyReport();
  const [asOf, setAsOf] = useState("");
  const [dlError, setDlError] = useState<string | null>(null);
  const error = runError ?? dlError;
  const [busy, setBusy] = useState<"" | "pdf" | "xlsx">("");
  const [selected, setSelected] = useState<string | null>(null);
  const detailRef = useRef<HTMLDivElement>(null);
  const { openChart } = useChart();
  // A sector's own index chart, with its RSI levels in the chart header.
  const openSectorChart = (s: SectorRow) => {
    if (s.equal_weight || !s.index_label) {
      // no index on Angel One: its index chart on TradingView
      if (s.tv_symbol) window.open(`https://www.tradingview.com/chart/?symbol=${encodeURIComponent(s.tv_symbol)}`, "_blank", "noopener");
      return;
    }
    openChart(s.index_label, {
      strategy: "Weekly Sectors",
      daily_rsi: s.rsi.d,
      weekly_rsi: s.rsi.w,
      monthly_rsi: s.rsi.m,
      signal_date: report?.end_date ?? null,
      explanation: `${s.label} (${s.index_label}): ${pct(s.r1w)} on the week (#${s.rank_1w}), ${pct(s.r1m)} on the month (#${s.rank_1m}) - ${s.verdict}.`,
      indicators: ALL_INDICATORS,
    });
  };

  // a new report starts on its first sector again
  useEffect(() => setSelected(null), [report?.generated_at]);

  function run() {
    setDlError(null);
    return runReport(asOf);
  }

  function dl(kind: "pdf" | "xlsx") {
    if (!report) return;
    setBusy(kind);
    (kind === "pdf" ? downloadWeeklyPdf(report) : downloadWeeklyXlsx(report))
      .catch((e) => setDlError(e instanceof Error ? e.message : "Download failed"))
      .finally(() => setBusy(""));
  }

  const sectorKey = selected ?? report?.sectors[0]?.key ?? null;
  const sector = report?.sectors.find((s) => s.key === sectorKey) ?? null;
  const pctDone = job && job.total ? Math.round((job.done / job.total) * 100) : 0;

  return (
    <div>
      <div className="page-header">
        <h1>Weekly Sectors</h1>
        <p className="page-subtitle">
          Which sector and which stocks are moving: 1-week and 1-month returns against each stock&apos;s own sector. A sector
          is STRONG when its daily, weekly and monthly RSI are all above 60.
        </p>
      </div>

      <div className="card">
        <div className="tb-config-grid">
          <div className="tb-field">
            <label>
              As of (optional)
              <input type="date" value={asOf} max={new Date().toISOString().slice(0, 10)} onChange={(e) => setAsOf(e.target.value)} />
            </label>
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginTop: 12 }}>
          <button className="primary-button" onClick={() => void run()} disabled={running}>
            {running ? "Running…" : "Run Report"}
          </button>
          <button className="secondary-button" onClick={() => dl("pdf")} disabled={!report || !!busy}>
            {busy === "pdf" ? "Preparing PDF…" : "Download PDF"}
          </button>
          <button className="secondary-button" onClick={() => dl("xlsx")} disabled={!report || !!busy}>
            {busy === "xlsx" ? "Preparing…" : "Download Excel"}
          </button>
          <span className="tb-config-hint">
            {running
              ? `${job?.phase} · ${job?.done}/${job?.total}${job?.current ? ` · ${job.current}` : ""}`
              : report
                ? `Showing the report for the week ending ${niceDate(report.end_date)} (made ${new Date(report.generated_at).toLocaleString("en-IN")}).`
                : "Leave the date empty for the latest close, then press Run Report (about 2–4 minutes: every sector and stock)."}
          </span>
        </div>
        {running && (
          <div className="wk-progress" aria-label="Progress">
            <span style={{ width: `${pctDone}%` }} />
          </div>
        )}
      </div>

      {error && (
        <div className="error-banner">
          <div>
            <strong>Could not build the report.</strong> {error}
          </div>
        </div>
      )}

      {report && (
        <>
          <div className="card">
            <h2 style={{ marginTop: 0 }}>What&apos;s moving — week ending {niceDate(report.end_date)}</h2>
            <div className="tb-summary-grid wk-kpis" style={{ marginTop: 12 }}>
              <div className="tb-summary-tile">
                <div className="tb-summary-label">Top sector</div>
                <div className="tb-summary-value">{report.summary.top_sector ?? "—"}</div>
                <div className="tb-config-hint" style={{ margin: 0 }}>
                  {pct(report.summary.top_sector_r1w)} 1W · {pct(report.summary.top_sector_r1m)} 1M
                </div>
              </div>
              <div className="tb-summary-tile">
                <div className="tb-summary-label">Strong sectors (RSI 60+)</div>
                <div className="tb-summary-value">{report.summary.strong_sectors.length}</div>
                <div className="tb-config-hint" style={{ margin: 0 }}>{report.summary.strong_sectors.join(", ") || "none"}</div>
              </div>
              <div className="tb-summary-tile">
                <div className="tb-summary-label">Beat sector on 1W & 1M</div>
                <div className="tb-summary-value wk-up">{report.summary.leaders}</div>
                <div className="tb-config-hint" style={{ margin: 0 }}>of {report.summary.rows} stock rows</div>
              </div>
              <div className="tb-summary-tile">
                <div className="tb-summary-label">Trail sector on both</div>
                <div className="tb-summary-value wk-down">{report.summary.laggards}</div>
                <div className="tb-config-hint" style={{ margin: 0 }}>of {report.summary.rows} stock rows</div>
              </div>
              <div className="tb-summary-tile">
                <div className="tb-summary-label">Nifty 50</div>
                <div className={`tb-summary-value ${tone(report.benchmark.r1w)}`}>{pct(report.benchmark.r1w)}</div>
                <div className="tb-config-hint" style={{ margin: 0 }}>1W · {pct(report.benchmark.r1m)} 1M</div>
              </div>
            </div>
            <ol className="wk-insights">
              {insights(report).map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ol>
          </div>

          <div className="wk-rank-grid">
            <RankPanel title="1-week ranking" sectors={report.sectors} field="r1w" />
            <RankPanel title="1-month ranking" sectors={report.sectors} field="r1m" />
          </div>

          <div className="card">
            <h2 style={{ marginTop: 0 }}>Sector scorecard</h2>
            {(["STRONG", "MIXED", "WEAK"] as const).map((group) => {
              const list = report.sectors
                .filter((x) => (x.verdict || "MIXED").toUpperCase() === group)
                .sort((p1, p2) => (p2.rsi.m ?? -1) - (p1.rsi.m ?? -1));
              if (!list.length) return null;
              return (
                <div key={group} className="ws-group">
                  <div className={`ws-group-head ws-group-${group.toLowerCase()}`}>
                    <span className="ws-group-dot" />
                    <b>{group === "STRONG" ? "Strong" : group === "MIXED" ? "Mixed" : "Weak"}</b>
                    <span className="ws-group-count">{list.length}</span>
                    <span className="muted small">{group === "STRONG" ? "daily, weekly and monthly RSI all above 60" : group === "WEAK" ? "all three below 40" : "in between"}</span>
                  </div>
            <div className="ws-grid">
              {list.map((s) => {
                const canChart = !!((!s.equal_weight && s.index_label) || s.tv_symbol);
                const v = (s.verdict || "").toUpperCase();
                return (
                  <div
                    key={s.key}
                    className={`ws-card ws-${v.toLowerCase()}${canChart ? " wk-click" : ""}`}
                    role={canChart ? "button" : undefined}
                    tabIndex={canChart ? 0 : undefined}
                    title={canChart ? `Open the ${s.index_label ?? s.label} chart` : undefined}
                    onClick={() => canChart && openSectorChart(s)}
                    onKeyDown={(e) => { if (canChart && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); openSectorChart(s); } }}
                  >
                    <div className="ws-head">
                      <SectorLogo sectorKey={s.key} />
                      <div className="ws-title">
                        <b>{s.label}</b>
                        <small>{s.equal_weight ? "equal-weight of its stocks" : s.index_label}</small>
                      </div>
                      <span className={verdictClass(s.verdict)}>{s.verdict}</span>
                    </div>
                    <div className="ws-rsi">
                      {(["d", "w", "m"] as const).map((k) => {
                        const r = s.rsi[k];
                        const cls = r === null ? "muted" : r > 60 ? "wk-up" : r < 40 ? "wk-down" : "wk-amber";
                        return (
                          <div key={k} className="ws-rsi-cell">
                            <span className="ws-rsi-top"><small>{k === "d" ? "Daily" : k === "w" ? "Weekly" : "Monthly"}</small><b className={cls}>{r === null ? "n/a" : r.toFixed(1)}</b></span>
                            <span className="ws-bar"><i className={cls} style={{ width: `${r === null ? 0 : Math.max(0, Math.min(100, r))}%` }} /><em /></span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
                </div>
              );
            })}
            <p className="muted small" style={{ marginBottom: 0 }}>
              STRONG = daily, weekly and monthly RSI(14) of the sector index all above 60; WEAK = all below 40; otherwise MIXED.
              ▲/▼ = places moved since last week. Click a sector to see its stocks.
            </p>
          </div>

          <div className="card" ref={detailRef}>
            <div className="wk-sector-chips">
              {report.sectors.map((s) => (
                <button key={s.key} type="button" className={s.key === sectorKey ? "active" : ""} onClick={() => setSelected(s.key)}>
                  {s.label}
                </button>
              ))}
            </div>
            {sector && (
              <>
                <div className="wk-sector-head">
                  <h2 style={{ margin: 0 }}>
                    {sector.label} <span className={verdictClass(sector.verdict)}>{sector.verdict}</span>
                  </h2>
                  {((!sector.equal_weight && sector.index_label) || sector.tv_symbol) && (
                    <ChartButton label={sector.index_label ?? sector.label} onOpen={() => openSectorChart(sector)} />
                  )}
                </div>
                <p className="muted small" style={{ marginTop: 0 }}>
                  Sector {pct(sector.r1w)} 1W (#{sector.rank_1w}) · {pct(sector.r1m)} 1M (#{sector.rank_1m}) · RSI D/W/M{" "}
                  {sector.rsi.d === null ? "n/a" : `${sector.rsi.d.toFixed(0)} / ${sector.rsi.w?.toFixed(0)} / ${sector.rsi.m?.toFixed(0)}`} ·
                  Leader {sector.counts["Leader"] ?? 0} · Turning up {sector.counts["Turning up"] ?? 0} · Fading {sector.counts["Fading"] ?? 0} ·
                  Laggard {sector.counts["Laggard"] ?? 0}
                  {sector.breadth?.label && ` · Breadth ${sector.breadth.label} (${sector.breadth.above_50dma}% above the 50-day average)`}
                </p>
                <StockTable rows={sector.stocks} sectorLabel={sector.label} endDate={report.end_date} />
              </>
            )}
          </div>

          <div>
            <div className="card">
              <h2 style={{ marginTop: 0 }}>Top movers</h2>
              <p className="muted small" style={{ marginTop: 0 }}>Beat their sector on 1W and 1M, by combined outperformance.</p>
              <StockTable rows={report.top_movers} withSector endDate={report.end_date} />
            </div>
            <div className="card">
              <h2 style={{ marginTop: 0 }}>Laggards</h2>
              <p className="muted small" style={{ marginTop: 0 }}>Trail their sector on 1W and 1M, deepest gaps first.</p>
              <StockTable rows={report.laggards} withSector endDate={report.end_date} />
            </div>
          </div>

          <div className="card">
            <h2 style={{ marginTop: 0 }}>Four study buckets</h2>
            <div className="wk-buckets">
              {BUCKETS.map(([key, title, sub, cls]) => (
                <div key={key} className={`wk-bucket ${cls}`}>
                  <div className="wk-bucket-head">
                    <strong>{title}</strong> <span>{sub}</span>
                  </div>
                  {Object.entries(report.buckets[key] ?? {}).length ? (
                    Object.entries(report.buckets[key]).map(([sec, syms]) => (
                      <p key={sec}>
                        <strong>{sec}:</strong> {syms.join(", ")}
                      </p>
                    ))
                  ) : (
                    <p className="muted">None this week.</p>
                  )}
                </div>
              ))}
            </div>
            <p className="muted small" style={{ marginBottom: 0 }}>
              1W / 1M = last close vs the close 7 days / 1 calendar month earlier, the same dates for every stock and sector. Sector
              lists: {report.constituents_source ?? "NSE"}. Capital Market has no index on Angel One: its line is the equal-weight
              average of its stocks.
              {report.missing.length > 0 && ` No data this time for: ${report.missing.join(", ")}.`} For education only; not investment
              advice.
            </p>
          </div>
          <ActionCard
            report={report}
            onStock={(st, label) =>
              openChart(st.symbol, {
                strategy: `Weekly Sectors · ${label}`,
                daily_rsi: st.rsi_d ?? null,
                weekly_rsi: null,
                monthly_rsi: null,
                signal_date: report.end_date,
                explanation: `${st.symbol}: ${pct(st.r1w)} 1W, ${pct(st.r1m)} 1M; leader of ${label}.`,
                indicators: ALL_INDICATORS,
              })
            }
            onSector={(key) => {
              setSelected(key);
              detailRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
            }}
          />
        </>
      )}
    </div>
  );
}
