import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  getGfsUniverse,
  gfsPagePath,
  startGfsUniverse,
  type GfsUniverse,
  type GfsUniverseRow,
  type GfsVariant,
} from "../services/gfsBacktestApi";

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}
function fmtRsi(v: number | null): string {
  return v === null ? "—" : v.toFixed(1);
}
function fmtPrice(v: number): string {
  return v.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

const TITLES: Record<GfsVariant, string> = { gfs: "GFS", advanced: "Advanced GFS", gfs50: "50 GFS" };
const RULES: Record<GfsVariant, string> = {
  gfs: "monthly RSI above 60, weekly RSI above 60 and daily RSI between 38 and 45",
  advanced: "monthly RSI, weekly RSI and daily RSI all above 60",
  gfs50: "monthly RSI above 60, weekly RSI above 60 and daily RSI above 50",
};

/** Every A Group stock that satisfies the strategy's backtest setup on its latest
 *  candle. The backend fetches ~600 stocks in the background; this page starts
 *  (or reuses) that run, polls its progress and shows the rows. */
export function GFSUniversePage({ variant }: { variant: GfsVariant }) {
  const title = TITLES[variant];
  const basePath = gfsPagePath(variant);
  const navigate = useNavigate();
  const [data, setData] = useState<GfsUniverse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  async function start(fresh: boolean) {
    setError(null);
    try {
      setData(await startGfsUniverse(variant, fresh));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start the stock list.");
    }
  }

  // Start (or reuse a cached) run when the page opens or the strategy changes.
  useEffect(() => {
    setData(null);
    void start(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [variant]);

  // Poll while the backend is still working.
  const running = data?.status === "running";
  useEffect(() => {
    if (!running) return;
    const id = window.setInterval(() => {
      getGfsUniverse(variant)
        .then(setData)
        .catch((e) => setError(e instanceof Error ? e.message : "Could not refresh progress."));
    }, 2000);
    return () => window.clearInterval(id);
  }, [running, variant]);

  const rows = useMemo<GfsUniverseRow[]>(() => {
    const q = query.trim().toLowerCase();
    const all = data?.rows ?? [];
    return q ? all.filter((r) => r.company_name.toLowerCase().includes(q) || r.symbol.toLowerCase().includes(q)) : all;
  }, [data, query]);

  function openChart(symbol: string) {
    // run=1 makes the backtest page run straight away so the chart is already there.
    navigate(`${basePath}?symbol=${encodeURIComponent(symbol)}&run=1`);
  }

  const pct = data && data.total > 0 ? Math.round((data.processed / data.total) * 100) : 0;

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <Link to={basePath} className="so-back-link">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M19 12H5" />
              <path d="m12 19-7-7 7-7" />
            </svg>
            {title} backtest
          </Link>
          <h1>{title} · All Stocks</h1>
          <p className="page-subtitle">
            A Group stocks whose latest daily candle meets the {title} setup: {RULES[variant]}. Weekly and monthly RSI use completed bars only,
            the same as the backtest. &quot;Data From / To&quot; is the range of daily candles that was read for the stock.
          </p>
        </div>
      </div>

      <div className="card">
        <div className="tb-actions">
          <input
            type="search"
            placeholder="Search company or symbol"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search company or symbol"
          />
          <button type="button" className="tb-btn tb-btn-secondary" onClick={() => void start(true)} disabled={running}>
            {running ? "Scanning…" : "Refresh"}
          </button>
          {data?.status === "done" && data.finished_at && (
            <span className="tb-config-hint">
              {data.rows.length} stocks · updated {new Date(`${data.finished_at}Z`).toLocaleString("en-IN")}
              {data.failed > 0 ? ` · ${data.failed} stocks had no data` : ""}
            </span>
          )}
        </div>
      </div>

      {error && (
        <div className="card state-block">
          <div className="state-title">Something went wrong</div>
          <div className="state-subtitle">{error}</div>
        </div>
      )}

      {running && (
        <div className="card state-block">
          <div className="state-title">
            Checking stocks… {data?.processed ?? 0} / {data?.total ?? 0} ({pct}%)
          </div>
          <div
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={pct}
            style={{ height: 6, borderRadius: 3, background: "var(--bg-hover)", overflow: "hidden", margin: "10px 0" }}
          >
            <div style={{ width: `${pct}%`, height: "100%", background: "var(--accent)", transition: "width 0.4s ease" }} />
          </div>
          <div className="state-subtitle">
            {data?.rows.length ?? 0} matching so far. Stocks are added to the list below as soon as they qualify; this takes a few minutes.
          </div>
        </div>
      )}

      {data?.status === "error" && (
        <div className="card state-block">
          <div className="state-title">The stock list could not be built</div>
          <div className="state-subtitle">{data.error}</div>
        </div>
      )}

      {data && data.status !== "error" && (
        <div className="card">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Company</th>
                  <th>Data From</th>
                  <th>Data To</th>
                  <th className="num-cell">Price</th>
                  <th className="num-cell">Daily RSI</th>
                  <th className="num-cell">Weekly RSI</th>
                  <th className="num-cell">Monthly RSI</th>
                  <th>In Setup Since</th>
                  <th>Chart</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={r.symbol}>
                    <td>{i + 1}</td>
                    <td>
                      <b>{r.company_name}</b>
                      <div className="muted small">{r.symbol}</div>
                    </td>
                    <td>{fmtDate(r.data_from)}</td>
                    <td>{fmtDate(r.data_to)}</td>
                    <td className="num-cell">{fmtPrice(r.close)}</td>
                    <td className="num-cell">{fmtRsi(r.daily_rsi)}</td>
                    <td className="num-cell">{fmtRsi(r.weekly_rsi)}</td>
                    <td className="num-cell">{fmtRsi(r.monthly_rsi)}</td>
                    <td>{fmtDate(r.in_setup_since)}</td>
                    <td>
                      <button type="button" className="tb-btn tb-btn-secondary" onClick={() => openChart(r.symbol)}>
                        Open chart
                      </button>
                    </td>
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr>
                    <td colSpan={10} style={{ textAlign: "center", padding: 16, opacity: 0.7 }}>
                      {running
                        ? "No matching stock found yet — still checking."
                        : query
                          ? "No stock matches your search."
                          : `No A Group stock meets the ${title} setup on its latest candle.`}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
