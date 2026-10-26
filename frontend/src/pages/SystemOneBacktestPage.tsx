import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { EquitySearchBox } from "./topBottom/EquitySearchBox";
import { SystemOneChart } from "./systemOne/SystemOneChart";
import { DEFAULT_TIMEFRAME, SYSTEM_ONE_TIMEFRAMES, isIntraday, timeframeNoun } from "./systemOne/timeframes";
import {
  runSystemOneBacktest,
  systemOneExportUrl,
  type SystemOneBacktest,
} from "../services/systemOneBacktestApi";

function fmtMoney(v: number | null | undefined): string {
  return v === null || v === undefined || Number.isNaN(v)
    ? "—"
    : v.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function fmtRupees(v: number | null | undefined): string {
  return v === null || v === undefined || Number.isNaN(v) ? "—" : `₹${fmtMoney(v)}`;
}
function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}
// Hourly candles keep their time of day; daily/weekly candles are just dates.
function fmtWhen(iso: string | null, intraday: boolean): string {
  if (!iso) return "—";
  if (!intraday) return fmtDate(iso);
  return new Date(iso).toLocaleString("en-IN", {
    day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false,
  });
}
function pnlColor(v: number | null | undefined): string | undefined {
  if (v === null || v === undefined || v === 0) return undefined;
  return v > 0 ? "var(--success)" : "var(--danger)";
}

const TODAY = new Date().toISOString().slice(0, 10);

export function SystemOneBacktestPage() {
  // Inputs live in the URL so a refresh or a shared link keeps the same stock and dates.
  const [params, setParams] = useSearchParams();
  const symbol = params.get("symbol") ?? "ADANIGREEN";
  const timeframe = params.get("tf") ?? DEFAULT_TIMEFRAME;
  const fromDate = params.get("from") ?? "2020-01-01";
  const toDate = params.get("to") ?? TODAY;
  function setParam(key: string, value: string) {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set(key, value);
        return next;
      },
      { replace: true },
    );
  }

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SystemOneBacktest | null>(null);
  const [focusedTrade, setFocusedTrade] = useState<number | null>(null);

  const invalidRange = fromDate > toDate;

  async function handleRun() {
    setError(null);
    setResult(null);
    setFocusedTrade(null);
    setLoading(true);
    try {
      setResult(
        await runSystemOneBacktest({
          symbol: symbol.trim().toUpperCase(),
          timeframe,
          from_date: `${fromDate}T00:00:00`,
          to_date: `${toDate}T23:59:59`,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Backtest failed.");
    } finally {
      setLoading(false);
    }
  }

  const s = result?.summary;
  const intraday = result ? isIntraday(result.timeframe) : false;

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <Link to="/strategies" className="so-back-link">
            ← Strategies
          </Link>
          <h1>System One</h1>
          <p className="page-subtitle">
            Trend-following backtest on the timeframe you pick (default weekly). Buy when RSI(14) crosses above 60 and
            enter at the next candle&apos;s close. Stop loss is the 20 MA at entry; exit when a candle closes below the
            20 MA. Risk is 1% of ₹10,00,000 (₹10,000) per trade.
          </p>
        </div>
      </div>

      <div className="card">
        <div className="tb-config-grid">
          <EquitySearchBox selected={symbol} onSelect={(v) => setParam("symbol", v)} />
          <div className="tb-field">
            <label>
              From Date
              <input type="date" value={fromDate} onChange={(e) => setParam("from", e.target.value)} />
            </label>
          </div>
          <div className="tb-field">
            <label>
              To Date
              <input type="date" value={toDate} onChange={(e) => setParam("to", e.target.value)} />
            </label>
          </div>
          <div className="tb-field">
            <label>
              Timeframe
              <select value={timeframe} onChange={(e) => setParam("tf", e.target.value)}>
                {SYSTEM_ONE_TIMEFRAMES.map((tf) => (
                  <option key={tf.value} value={tf.value}>
                    {tf.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>
        <div className="tb-actions">
          <button
            type="button"
            className="tb-btn tb-btn-primary"
            onClick={handleRun}
            disabled={loading || !symbol.trim() || invalidRange}
          >
            {loading && <span className="tb-spinner" aria-hidden="true" />}
            {loading ? "Running…" : "Run Backtest"}
          </button>
          {result && (
            <a href={systemOneExportUrl(result.backtest_id)}>
              <button type="button" className="tb-btn tb-btn-secondary">
                Download Excel
              </button>
            </a>
          )}
          {invalidRange && <span className="tb-config-hint">From Date must not be after To Date.</span>}
        </div>
      </div>

      {loading && (
        <div className="card state-block">
          <div className="state-title">Running System One backtest…</div>
          <div className="state-subtitle">Fetching weekly candles and simulating trades</div>
        </div>
      )}

      {error && !loading && (
        <div className="card state-block">
          <div className="state-title">Backtest could not run</div>
          <div className="state-subtitle">{error}</div>
        </div>
      )}

      {!result && !loading && !error && (
        <div className="card state-block">
          <div className="state-title">Pick a stock and a date range</div>
          <div className="state-subtitle">Run the backtest to see the chart, trades and results here.</div>
        </div>
      )}

      {result && s && !loading && (
        <>
          {result.warnings.map((w) => (
            <div key={w} className="error-banner small">
              {w}
            </div>
          ))}

          <div className="card">
            <h2 style={{ marginTop: 0 }}>
              {result.symbol} · {result.timeframe} · {fmtDate(result.from_date)} – {fmtDate(result.to_date)}
            </h2>
            <div className="tb-summary-grid">
              <Tile label="Total Trades" value={`${s.total_trades}`} sub={`${s.closed_trades} closed · ${s.open_trades} open`} />
              <Tile label="Net Realised P&L" value={fmtRupees(s.net_realized_pnl)} color={pnlColor(s.net_realized_pnl)} />
              <Tile label="Win Rate" value={s.win_rate === null ? "—" : `${s.win_rate.toFixed(1)}%`} sub={`${s.winning_trades}W · ${s.losing_trades}L`} />
              <Tile label="Profit Factor" value={s.profit_factor === null ? "—" : s.profit_factor.toFixed(2)} />
              <Tile label="Average Win" value={fmtRupees(s.average_win)} color={pnlColor(s.average_win)} />
              <Tile label="Average Loss" value={fmtRupees(s.average_loss)} color={pnlColor(s.average_loss)} />
              <Tile label="Best Trade" value={fmtRupees(s.best_trade)} color={pnlColor(s.best_trade)} />
              <Tile label="Worst Trade" value={fmtRupees(s.worst_trade)} color={pnlColor(s.worst_trade)} />
            </div>
            {s.closed_trades > 0 && s.closed_trades < 30 && (
              <p className="tb-config-hint" style={{ marginBottom: 0 }}>
                Only {s.closed_trades} closed trade{s.closed_trades === 1 ? "" : "s"} — too few to judge the strategy from
                these statistics alone.
              </p>
            )}
          </div>

          <div className="card">
            <h2 style={{ marginTop: 0 }}>Chart</h2>
            <SystemOneChart key={result.backtest_id} result={result} focusedTradeNumber={focusedTrade} />
          </div>

          <div className="card">
            <h2 style={{ marginTop: 0 }}>Trades</h2>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Entry Date</th>
                    <th className="num-cell">Entry Price</th>
                    <th className="num-cell">Stop Loss</th>
                    <th className="num-cell">Risk Per Share</th>
                    <th className="num-cell">Risk Per Trade</th>
                    <th className="num-cell">Quantity</th>
                    <th className="num-cell">Exit Price</th>
                    <th>Exit Date</th>
                    <th className="num-cell">P&amp;L Amount</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {result.trades.map((t) => (
                    <tr
                      key={t.trade_number}
                      onClick={() => setFocusedTrade((cur) => (cur === t.trade_number ? null : t.trade_number))}
                      className={focusedTrade === t.trade_number ? "tb-row-focused" : ""}
                      style={{ cursor: "pointer" }}
                    >
                      <td>{fmtWhen(t.entry_date, intraday)}</td>
                      <td className="num-cell">{fmtMoney(t.entry_price)}</td>
                      <td className="num-cell">{fmtMoney(t.stop_loss)}</td>
                      <td className="num-cell">{fmtMoney(t.risk_per_share)}</td>
                      <td className="num-cell">{fmtMoney(t.risk_per_trade)}</td>
                      <td className="num-cell">{t.quantity}</td>
                      <td className="num-cell">{t.exit_price === null ? "—" : fmtMoney(t.exit_price)}</td>
                      <td>{fmtWhen(t.exit_date, intraday)}</td>
                      <td className="num-cell" style={{ color: pnlColor(t.pnl_amount) }}>
                        {t.pnl_amount === null ? "—" : fmtMoney(t.pnl_amount)}
                      </td>
                      <td>
                        <span className={`badge ${t.status === "OPEN" ? "badge-neutral" : "badge-good"}`}>
                          {t.status === "OPEN" ? "Open" : "Closed"}
                        </span>
                      </td>
                    </tr>
                  ))}
                  {result.trades.length === 0 && (
                    <tr>
                      <td colSpan={10} style={{ textAlign: "center", padding: 16, opacity: 0.7 }}>
                        No System One trades in this period.
                        {result.skipped_signals.length > 0 ? " Some signals were skipped — see below." : ""}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {result.skipped_signals.length > 0 && (
              <ul className="tb-config-hint" style={{ marginTop: 12 }}>
                {result.skipped_signals.map((sk) => (
                  <li key={sk.signal_date}>
                    Signal {fmtWhen(sk.signal_date, intraday)} skipped: {sk.reason}
                  </li>
                ))}
              </ul>
            )}

            <p className="tb-config-hint" style={{ marginBottom: 0 }}>
              {result.note} {timeframeNoun(result.timeframe)} candles available {fmtWhen(result.data_available_from, intraday)} –{" "}
              {fmtWhen(result.data_available_to, intraday)}; the candle still in progress is not used. Open trades show “—”
              for exit and P&amp;L because nothing is realised yet.
            </p>
          </div>
        </>
      )}
    </div>
  );
}

function Tile({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div className="tb-summary-tile">
      <div className="tb-summary-label">{label}</div>
      <div className="tb-summary-value" style={{ color }}>
        {value}
      </div>
      {sub && <div className="tb-config-hint" style={{ margin: 0 }}>{sub}</div>}
    </div>
  );
}
