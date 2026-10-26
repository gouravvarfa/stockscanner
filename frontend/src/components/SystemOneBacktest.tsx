import { useState } from "react";
import { EquitySearchBox } from "../pages/topBottom/EquitySearchBox";
import {
  runSystemOneBacktest,
  systemOneExportUrl,
  type SystemOneBacktest as BacktestResult,
} from "../services/systemOneBacktestApi";

function fmtMoney(v: number | null | undefined): string {
  return v === null || v === undefined || Number.isNaN(v)
    ? "—"
    : v.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}
function pnlColor(v: number | null): string | undefined {
  if (v === null || v === 0) return undefined;
  return v > 0 ? "var(--success)" : "var(--danger)";
}

export function SystemOneBacktest() {
  const [symbol, setSymbol] = useState("ADANIGREEN");
  const [fromDate, setFromDate] = useState("2020-01-01");
  const [toDate, setToDate] = useState(new Date().toISOString().slice(0, 10));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BacktestResult | null>(null);

  async function handleRun() {
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      setResult(
        await runSystemOneBacktest({
          symbol: symbol.trim().toUpperCase(),
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

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h2 style={{ marginTop: 0 }}>System One Backtest</h2>
      <p className="page-subtitle" style={{ marginTop: 0 }}>
        Weekly candles. Buy when RSI(14) crosses above 60, entering at the next week&apos;s close. Stop loss = 20 MA at
        entry. Exit when a weekly close falls below the 20 MA. Risk 1% of ₹10,00,000 (₹10,000) per trade.
      </p>

      <div className="tb-config-grid">
        <EquitySearchBox selected={symbol} onSelect={setSymbol} />
        <div className="tb-field">
          <label>
            From Date
            <input type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} />
          </label>
        </div>
        <div className="tb-field">
          <label>
            To Date
            <input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} />
          </label>
        </div>
      </div>

      <div className="tb-actions">
        <button
          type="button"
          className="tb-btn tb-btn-primary"
          onClick={handleRun}
          disabled={loading || !symbol.trim() || fromDate > toDate}
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
        {fromDate > toDate && <span className="tb-config-hint">From Date must not be after To Date.</span>}
      </div>

      {error && !loading && (
        <div className="state-block">
          <div className="state-title">Backtest could not run</div>
          <div className="state-subtitle">{error}</div>
        </div>
      )}

      {result && !loading && (
        <>
          <p className="tb-selected-line">
            <strong>{result.symbol}</strong> · System One · Weekly · {fmtDate(result.from_date)} –{" "}
            {fmtDate(result.to_date)} · {result.summary.total_trades} trades ({result.summary.closed_trades} closed,{" "}
            {result.summary.open_trades} open) · Net realised P&amp;L{" "}
            <strong style={{ color: pnlColor(result.summary.net_realized_pnl) }}>
              ₹{fmtMoney(result.summary.net_realized_pnl)}
            </strong>
          </p>

          {result.warnings.map((w) => (
            <div key={w} className="error-banner small">
              {w}
            </div>
          ))}

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
                  <tr key={t.trade_number}>
                    <td>{fmtDate(t.entry_date)}</td>
                    <td className="num-cell">{fmtMoney(t.entry_price)}</td>
                    <td className="num-cell">{fmtMoney(t.stop_loss)}</td>
                    <td className="num-cell">{fmtMoney(t.risk_per_share)}</td>
                    <td className="num-cell">{fmtMoney(t.risk_per_trade)}</td>
                    <td className="num-cell">{t.quantity}</td>
                    <td className="num-cell">{t.exit_price === null ? "—" : fmtMoney(t.exit_price)}</td>
                    <td>{fmtDate(t.exit_date)}</td>
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
              {result.skipped_signals.map((s) => (
                <li key={s.signal_date}>
                  Signal {fmtDate(s.signal_date)} skipped: {s.reason}
                </li>
              ))}
            </ul>
          )}

          <p className="tb-config-hint" style={{ marginTop: 12 }}>
            {result.note} Data available {fmtDate(result.data_available_from)} – {fmtDate(result.data_available_to)}.
            Open trades show “—” for exit and P&amp;L (not realised).
          </p>
        </>
      )}
    </div>
  );
}
