import { useEffect, useMemo, useState } from "react";
import { api, type TradingViewSignal, type TradingViewStatus } from "../services/api";

const STRATEGIES = ["Strategy One", "GFS", "Advanced GFS", "PRD", "NRD", "Value Buy"];

function fmt(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined || Number.isNaN(value) ? "—" : value.toFixed(digits);
}

function fmtDate(value: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString();
}

// Distinguishes: existing market-data provider (scanner's own scans) /
// TradingView webhook signal (this page) / TradingView signal received /
// TradingView not configured / TradingView signal unavailable. Never shows
// "connected" without a real status response confirming it.
function StatusBanner({ status }: { status: TradingViewStatus | null }) {
  if (status === null) {
    return (
      <div className="card state-block">
        <div className="state-title">TradingView signal unavailable</div>
        <div className="state-subtitle">Could not reach the backend's TradingView status endpoint.</div>
      </div>
    );
  }
  if (!status.enabled || !status.configured) {
    return (
      <div className="card state-block">
        <div className="state-title">TradingView not configured</div>
        <div className="state-subtitle">
          Set TRADINGVIEW_ENABLED=true and TRADINGVIEW_WEBHOOK_SECRET in the backend's .env, then restart the
          backend. This is a separate, optional signal source — the existing scanner (Tapetide/Angel One) is
          completely unaffected either way.
        </div>
      </div>
    );
  }
  return (
    <div className="card state-block" style={{ textAlign: "left" }}>
      <div className="state-title">TradingView webhook signal — configured</div>
      <div className="state-subtitle">
        {status.signal_count} signal{status.signal_count === 1 ? "" : "s"} received so far
        {status.latest_signal_at ? `, latest at ${fmtDate(status.latest_signal_at)}` : ""}. This list only shows
        signals TradingView alerts have actually delivered to the webhook — it is not a live scan of NIFTY 200.
      </div>
    </div>
  );
}

export function TradingViewSignals() {
  const [status, setStatus] = useState<TradingViewStatus | null>(null);
  const [signals, setSignals] = useState<TradingViewSignal[]>([]);
  const [loading, setLoading] = useState(true);
  const [strategyFilter, setStrategyFilter] = useState("all");
  const [symbolSearch, setSymbolSearch] = useState("");
  const [timeframeFilter, setTimeframeFilter] = useState("all");

  function refresh() {
    setLoading(true);
    Promise.all([api.getTradingViewStatus().catch(() => null), api.listTradingViewSignals().catch(() => [])]).then(
      ([s, sigs]) => {
        setStatus(s);
        setSignals(sigs);
        setLoading(false);
      },
    );
  }

  useEffect(() => {
    refresh();
  }, []);

  const timeframes = useMemo(() => {
    const set = new Set(signals.map((s) => s.signal_timeframe).filter(Boolean));
    return ["all", ...Array.from(set).sort()];
  }, [signals]);

  // Local-only filtering against already-fetched signals — no new
  // market-data or webhook calls are triggered by changing a filter.
  const filtered = useMemo(() => {
    let rows = signals;
    if (strategyFilter !== "all") rows = rows.filter((s) => s.strategy === strategyFilter);
    if (timeframeFilter !== "all") rows = rows.filter((s) => s.signal_timeframe === timeframeFilter);
    if (symbolSearch.trim()) {
      const q = symbolSearch.trim().toUpperCase();
      rows = rows.filter((s) => s.symbol.toUpperCase().includes(q));
    }
    return rows;
  }, [signals, strategyFilter, timeframeFilter, symbolSearch]);

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>TradingView Signals</h1>
          <p className="page-subtitle">
            Optional, alert-driven signal source from a TradingView Pine Script — additional to, never a replacement
            for, the scanner's own Tapetide/Angel One-driven scans.
          </p>
        </div>
        <button onClick={refresh} disabled={loading}>
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      <StatusBanner status={status} />

      {status?.configured && (
        <>
          <div className="card filters-row">
            <label>
              Search symbol
              <input type="text" value={symbolSearch} onChange={(e) => setSymbolSearch(e.target.value)} placeholder="e.g. RELIANCE" />
            </label>
            <label>
              Strategy
              <select value={strategyFilter} onChange={(e) => setStrategyFilter(e.target.value)}>
                <option value="all">All Strategies</option>
                {STRATEGIES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Timeframe
              <select value={timeframeFilter} onChange={(e) => setTimeframeFilter(e.target.value)}>
                {timeframes.map((t) => (
                  <option key={t} value={t}>
                    {t === "all" ? "All Timeframes" : t}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {filtered.length === 0 ? (
            <div className="card state-block">
              <div className="state-title">No signals found</div>
              <div className="state-subtitle">
                {signals.length === 0
                  ? "No TradingView alerts have been received yet. Set up the Pine Script alert per docs/tradingview_webhook.md."
                  : "No signals match the current filters."}
              </div>
            </div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Strategy</th>
                    <th>Timeframe</th>
                    <th>Signal Date</th>
                    <th className="num-cell">Daily RSI</th>
                    <th className="num-cell">Weekly RSI</th>
                    <th className="num-cell">Monthly RSI</th>
                    <th>Trigger</th>
                    <th>Divergence TF</th>
                    <th>Source</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((s) => (
                    <tr key={s.id}>
                      <td className="symbol-cell">{s.symbol}</td>
                      <td>{s.strategy}</td>
                      <td>{s.signal_timeframe}</td>
                      <td>{fmtDate(s.signal_date)}</td>
                      <td className="num-cell">{fmt(s.daily_rsi)}</td>
                      <td className="num-cell">{fmt(s.weekly_rsi)}</td>
                      <td className="num-cell">{fmt(s.monthly_rsi)}</td>
                      <td>{s.trigger ?? "—"}</td>
                      <td>{s.divergence_timeframe ?? "—"}</td>
                      <td>
                        <span className="chip chip-pass">TradingView webhook signal</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
