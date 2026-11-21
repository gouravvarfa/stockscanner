import { useEffect, useRef, useState } from "react";
import {
  downloadWeeklyPdf,
  downloadWeeklyXlsx,
  getWeeklyJob,
  loadLastReport,
  saveLastReport,
  startWeeklyReport,
  type SectorRow,
  type SectorStock,
  type WeeklyJob,
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

function StockTable({ rows, withSector }: { rows: SectorStock[]; withSector?: boolean }) {
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
                {s.symbol}
                {s.name && <span className="wk-name">{s.name}</span>}
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
  const [report, setReport] = useState<WeeklyReport | null>(() => loadLastReport());
  const [asOf, setAsOf] = useState("");
  const [job, setJob] = useState<WeeklyJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"" | "pdf" | "xlsx">("");
  const [selected, setSelected] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const detailRef = useRef<HTMLDivElement>(null);

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  const running = job?.status === "running";

  function finish(j: WeeklyJob) {
    setJob(j);
    if (j.status === "done" && j.result) {
      setReport(j.result);
      saveLastReport(j.result);
      setSelected(null);
    } else if (j.status === "failed") {
      setError(j.error ?? "The report could not be built.");
    }
  }

  async function run() {
    setError(null);
    try {
      const j = await startWeeklyReport(asOf);
      if (j.status !== "running") return finish(j);
      setJob(j);
      const poll = async () => {
        try {
          const next = await getWeeklyJob(j.job_id);
          if (next.status === "running") {
            setJob(next);
            timer.current = setTimeout(poll, 1500);
          } else finish(next);
        } catch (e) {
          setJob(null);
          setError(e instanceof Error ? e.message : String(e));
        }
      };
      timer.current = setTimeout(poll, 1200);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  function dl(kind: "pdf" | "xlsx") {
    if (!report) return;
    setBusy(kind);
    (kind === "pdf" ? downloadWeeklyPdf(report) : downloadWeeklyXlsx(report))
      .catch((e) => setError(e instanceof Error ? e.message : "Download failed"))
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
            <div className="tb-summary-grid" style={{ marginTop: 12 }}>
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
            <div className="table-wrap">
              <table className="wk-table">
                <thead>
                  <tr>
                    <th>Sector</th>
                    <th>1W %</th>
                    <th>#</th>
                    <th>1M %</th>
                    <th>#</th>
                    <th>RSI D</th>
                    <th>RSI W</th>
                    <th>RSI M</th>
                    <th>Beat 1W | 1M</th>
                    <th>Verdict</th>
                  </tr>
                </thead>
                <tbody>
                  {report.sectors.map((s) => (
                    <tr
                      key={s.key}
                      className="wk-click"
                      onClick={() => {
                        setSelected(s.key);
                        detailRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
                      }}
                    >
                      <td className="wk-sym">
                        {s.label}
                        <span className="wk-name">{s.equal_weight ? "equal-weight of its stocks" : s.index_label}</span>
                      </td>
                      <td className={tone(s.r1w)}>{pct(s.r1w)}</td>
                      <td>#{s.rank_1w}</td>
                      <td className={tone(s.r1m)}>{pct(s.r1m)}</td>
                      <td>#{s.rank_1m}</td>
                      {(["d", "w", "m"] as const).map((k) => {
                        const v = s.rsi[k];
                        return (
                          <td key={k} className={v === null ? "muted" : v > 60 ? "wk-up" : v < 40 ? "wk-down" : "wk-amber"}>
                            {v === null ? "n/a" : v.toFixed(1)}
                          </td>
                        );
                      })}
                      <td>
                        {s.beat_1w}/{s.stocks.length} | {s.beat_1m}/{s.stocks.length}
                      </td>
                      <td>
                        <span className={verdictClass(s.verdict)}>{s.verdict}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted small" style={{ marginBottom: 0 }}>
              STRONG = daily, weekly and monthly RSI(14) of the sector index all above 60; WEAK = all below 40; otherwise MIXED.
              Click a sector to see its stocks.
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
                <h2 style={{ margin: "12px 0 4px" }}>
                  {sector.label} <span className={verdictClass(sector.verdict)}>{sector.verdict}</span>
                </h2>
                <p className="muted small" style={{ marginTop: 0 }}>
                  Sector {pct(sector.r1w)} 1W (#{sector.rank_1w}) · {pct(sector.r1m)} 1M (#{sector.rank_1m}) · RSI D/W/M{" "}
                  {sector.rsi.d === null ? "n/a" : `${sector.rsi.d.toFixed(0)} / ${sector.rsi.w?.toFixed(0)} / ${sector.rsi.m?.toFixed(0)}`} ·
                  Leader {sector.counts["Leader"] ?? 0} · Turning up {sector.counts["Turning up"] ?? 0} · Fading {sector.counts["Fading"] ?? 0} ·
                  Laggard {sector.counts["Laggard"] ?? 0}
                </p>
                <StockTable rows={sector.stocks} />
              </>
            )}
          </div>

          <div>
            <div className="card">
              <h2 style={{ marginTop: 0 }}>Top movers</h2>
              <p className="muted small" style={{ marginTop: 0 }}>Beat their sector on 1W and 1M, by combined outperformance.</p>
              <StockTable rows={report.top_movers} withSector />
            </div>
            <div className="card">
              <h2 style={{ marginTop: 0 }}>Laggards</h2>
              <p className="muted small" style={{ marginTop: 0 }}>Trail their sector on 1W and 1M, deepest gaps first.</p>
              <StockTable rows={report.laggards} withSector />
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
        </>
      )}
    </div>
  );
}
