import { InstrumentBadge } from "../components/InstrumentBadge";
import { useMemo, useState } from "react";
import { EquityCurveChart } from "./topBottom/EquityCurveChart";
import { EquitySearchBox } from "./topBottom/EquitySearchBox";
import { FuturesSearchBox } from "./topBottom/FuturesSearchBox";
import { TopBottomChart } from "./topBottom/TopBottomChart";
import {
  TOP_BOTTOM_TIMEFRAMES,
  exportBacktestUrl,
  runBacktest,
  type BacktestResult,
  type FutureContract,
  type TopBottomTrade,
} from "../services/topBottomApi";

function fmtPct(v: number | null | undefined, digits = 2): string {
  return v === null || v === undefined || Number.isNaN(v) ? "—" : `${v.toFixed(digits)}%`;
}
function fmtNum(v: number | null | undefined, digits = 2): string {
  return v === null || v === undefined || Number.isNaN(v) ? "—" : v.toFixed(digits);
}
function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

const LOADING_STEPS = [
  "Loading data",
  "Detecting Tops/Bottoms",
  "Generating signals",
  "Simulating trailing-stop trades",
  "Calculating statistics",
  "Preparing results",
];

type DirectionFilter = "ALL" | "BUY" | "SELL";
type ResultFilter = "ALL" | "WIN" | "LOSS";
type ExitFilter = "ALL" | "TRAILING_STOP_REVERSAL" | "END_OF_BACKTEST";

type Segment = "EQUITY" | "FUTURES";

export function TopBottomBacktest() {
  const [segment, setSegment] = useState<Segment>("EQUITY");
  const [equitySymbol, setEquitySymbol] = useState("ADANIGREEN");
  const [contract, setContract] = useState<FutureContract | null>(null);
  const [fromDate, setFromDate] = useState("2025-01-01");
  const [toDate, setToDate] = useState(new Date().toISOString().slice(0, 10));
  const [timeframe, setTimeframe] = useState("1D");

  const [loading, setLoading] = useState(false);
  const [loadingStep, setLoadingStep] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [focusedTrade, setFocusedTrade] = useState<number | null>(null);

  const [directionFilter, setDirectionFilter] = useState<DirectionFilter>("ALL");
  const [resultFilter, setResultFilter] = useState<ResultFilter>("ALL");
  const [exitFilter, setExitFilter] = useState<ExitFilter>("ALL");

  async function handleRunBacktest() {
    if (segment === "FUTURES" && !contract) {
      setError("Select a futures contract first.");
      return;
    }
    if (segment === "EQUITY" && !equitySymbol.trim()) {
      setError("Enter an NSE equity symbol first.");
      return;
    }
    setError(null);
    setResult(null);
    setFocusedTrade(null);
    setLoading(true);
    setLoadingStep(0);

    const stepTimer = setInterval(() => {
      setLoadingStep((s) => Math.min(s + 1, LOADING_STEPS.length - 1));
    }, 500);

    try {
      const res = await runBacktest({
        symbol: segment === "EQUITY" ? equitySymbol.trim().toUpperCase() : contract!.underlying,
        instrument_type: segment,
        expiry: segment === "FUTURES" ? contract!.expiry : null,
        timeframe,
        from_date: `${fromDate}T00:00:00`,
        to_date: `${toDate}T23:59:59`,
        starting_capital: 100,
      });
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Backtest failed.");
    } finally {
      clearInterval(stepTimer);
      setLoading(false);
    }
  }

  function handleReset() {
    setContract(null);
    setResult(null);
    setError(null);
    setFocusedTrade(null);
    setDirectionFilter("ALL");
    setResultFilter("ALL");
    setExitFilter("ALL");
  }

  const filteredTrades: TopBottomTrade[] = useMemo(() => {
    if (!result) return [];
    return result.trades.filter((t) => {
      if (directionFilter !== "ALL" && t.direction !== directionFilter) return false;
      if (resultFilter === "WIN" && t.status !== "WIN") return false;
      if (resultFilter === "LOSS" && t.status !== "LOSS") return false;
      if (exitFilter !== "ALL" && t.exit_reason !== exitFilter) return false;
      return true;
    });
  }, [result, directionFilter, resultFilter, exitFilter]);

  const filtersActive = directionFilter !== "ALL" || resultFilter !== "ALL" || exitFilter !== "ALL";

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Top Bottom Backtesting</h1>
          <p className="page-subtitle">
            Independent futures-only backtest — always-in-market trailing stop &amp; reverse on close-price Tops/Bottoms.
            Never run on cash/equity.
          </p>
        </div>
      </div>

      <div className="card">
        <h2 style={{ marginTop: 0 }}>Backtest Configuration</h2>
        <div className="tb-config-grid">
          <div className="tb-field">
            <label>
              Segment
              <select
                value={segment}
                onChange={(e) => {
                  setSegment(e.target.value as Segment);
                  setResult(null);
                  setError(null);
                }}
              >
                <option value="EQUITY">NSE Equity</option>
                <option value="FUTURES">NFO Futures</option>
              </select>
            </label>
          </div>
          {segment === "EQUITY" ? (
            <EquitySearchBox selected={equitySymbol} onSelect={setEquitySymbol} />
          ) : (
            <FuturesSearchBox selected={contract} onSelect={setContract} />
          )}
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
          <div className="tb-field">
            <label>
              Timeframe
              <select value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>
                {TOP_BOTTOM_TIMEFRAMES.map((tf) => (
                  <option key={tf} value={tf}>{tf}</option>
                ))}
              </select>
            </label>
          </div>
        </div>

        <div className="tb-actions">
          <button
            type="button"
            className="tb-btn tb-btn-primary"
            onClick={handleRunBacktest}
            disabled={loading || (segment === "FUTURES" ? !contract : !equitySymbol.trim())}
          >
            {loading && <span className="tb-spinner" aria-hidden="true" />}
            {loading ? "Running…" : "Run Backtest"}
          </button>
          <button type="button" className="tb-btn tb-btn-secondary" onClick={handleReset} disabled={loading}>
            Reset
          </button>
          {result && (
            <a href={exportBacktestUrl(result.backtest_id)}>
              <button type="button" className="tb-btn tb-btn-secondary">
                Export Excel
              </button>
            </a>
          )}
          {!loading && segment === "FUTURES" && !contract && (
            <span className="tb-config-hint">Select a futures contract to enable Run Backtest.</span>
          )}
          {!loading && segment === "EQUITY" && !equitySymbol.trim() && (
            <span className="tb-config-hint">Select an A Group equity to enable Run Backtest.</span>
          )}
        </div>

        {segment === "EQUITY" ? (
          <p className="tb-selected-line">
            Selected: <strong>{equitySymbol || "—"}</strong> · NSE Cash Equity (A Group list) · P&amp;L per share
          </p>
        ) : (
          contract && (
            <p className="tb-selected-line">
              Selected: <strong>{contract.underlying} FUT</strong> · Expiry {contract.expiry} · {contract.exch_seg}
              {contract.is_index ? " · Index Future" : " · Stock Future"}
            </p>
          )
        )}
      </div>

      {loading && (
        <div className="card state-block">
          <div className="state-title">Running Top-Bottom Backtest…</div>
          <div className="state-subtitle">{LOADING_STEPS[loadingStep]}</div>
        </div>
      )}

      {error && !loading && (
        <div className="card state-block">
          <div className="state-title">Backtest could not run</div>
          <div className="state-subtitle">{error}</div>
        </div>
      )}

      {result && !loading && (
        <>
          {!result.coverage.is_complete && (
            <div className="card state-block">
              <div className="state-title">Backtest marked incomplete</div>
              <div className="state-subtitle">
                Requested {fmtDate(result.coverage.requested_from)} – {fmtDate(result.coverage.requested_to)}, but{" "}
                {result.trading_symbol} data is only available {fmtDate(result.coverage.available_from)} –{" "}
                {fmtDate(result.coverage.available_to)}. Results reflect only the available range.
              </div>
            </div>
          )}

          <div className="card">
            <h2 style={{ marginTop: 0 }}>
              Backtest Summary — {result.symbol}
              <InstrumentBadge type={result.instrument_type} />
            </h2>
            <div className="tb-summary-grid">
              <SummaryTile label="Total Signals" value={result.statistics.total_signals} />
              <SummaryTile label="Buy Signals" value={result.statistics.buy_signals} />
              <SummaryTile label="Sell Signals" value={result.statistics.sell_signals} />
              <SummaryTile label="Winning Trades" value={result.statistics.winning_trades} />
              <SummaryTile label="Losing Trades" value={result.statistics.losing_trades} />
              <SummaryTile label="Win Rate" value={fmtPct(result.statistics.win_rate)} />
              <SummaryTile label="Net P&L %" value={fmtPct(result.statistics.net_pnl_pct)} />
              <SummaryTile label="Average Trade %" value={fmtPct(result.statistics.average_trade_pct)} />
              <SummaryTile label="Best Trade %" value={fmtPct(result.statistics.best_trade_pct)} />
              <SummaryTile label="Worst Trade %" value={fmtPct(result.statistics.worst_trade_pct)} />
              <SummaryTile label="Profit Factor" value={result.statistics.profit_factor === null ? "N/A" : fmtNum(result.statistics.profit_factor)} />
              <SummaryTile label="Max Drawdown" value={fmtPct(result.statistics.max_drawdown_pct)} />
              <SummaryTile label="Avg Holding (days)" value={fmtNum(result.statistics.average_holding_days, 1)} />
            </div>
          </div>

          <div className="card">
            <h2 style={{ marginTop: 0 }}>Price / Signal Chart</h2>
            <TopBottomChart result={result} focusedTradeNumber={focusedTrade} />
          </div>

          <div className="card">
            <h2 style={{ marginTop: 0 }}>Trade Results</h2>
            <div className="filters-row" style={{ marginBottom: 12 }}>
              <label>
                Direction
                <select value={directionFilter} onChange={(e) => setDirectionFilter(e.target.value as DirectionFilter)}>
                  <option value="ALL">ALL</option>
                  <option value="BUY">BUY</option>
                  <option value="SELL">SELL</option>
                </select>
              </label>
              <label>
                Result
                <select value={resultFilter} onChange={(e) => setResultFilter(e.target.value as ResultFilter)}>
                  <option value="ALL">ALL</option>
                  <option value="WIN">WIN</option>
                  <option value="LOSS">LOSS</option>
                </select>
              </label>
              <label>
                Exit Reason
                <select value={exitFilter} onChange={(e) => setExitFilter(e.target.value as ExitFilter)}>
                  <option value="ALL">ALL</option>
                  <option value="TRAILING_STOP_REVERSAL">TRAILING STOP REVERSAL</option>
                  <option value="END_OF_BACKTEST">END OF BACKTEST</option>
                </select>
              </label>
              {filtersActive && <span style={{ alignSelf: "center", fontSize: 12, opacity: 0.7 }}>Filters active — showing {filteredTrades.length}/{result.trades.length} trades</span>}
            </div>

            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>#</th><th>Date</th><th>Symbol</th><th>Direction</th>
                    <th className="num-cell">System Point</th>
                    <th className="num-cell">Entry</th><th className="num-cell">Initial SL</th>
                    <th className="num-cell">Trailing Stop (at exit)</th>
                    <th className="num-cell">Exit</th><th>Exit Date</th><th>Exit Reason</th>
                    <th className="num-cell">P&L %</th><th className="num-cell">P&L Pts</th><th className="num-cell">P&L (Rs.)</th><th className="num-cell">Holding</th><th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTrades.map((t) => (
                    <tr
                      key={t.trade_number}
                      onClick={() => setFocusedTrade((cur) => (cur === t.trade_number ? null : t.trade_number))}
                      className={focusedTrade === t.trade_number ? "tb-row-focused" : ""}
                      style={{ cursor: "pointer" }}
                    >
                      <td>{t.trade_number}</td>
                      <td>{fmtDate(t.entry_date)}</td>
                      <td>{t.trading_symbol}</td>
                      <td>{t.direction}</td>
                      <td className="num-cell">{fmtNum(t.system_point)}</td>
                      <td className="num-cell">{fmtNum(t.entry_price)}</td>
                      <td className="num-cell">{fmtNum(t.initial_sl)}</td>
                      <td className="num-cell">{fmtNum(t.active_stop)}</td>
                      <td className="num-cell">{fmtNum(t.exit_price)}</td>
                      <td>{fmtDate(t.exit_date)}</td>
                      <td>{t.exit_reason ?? "—"}</td>
                      <td className="num-cell">{fmtPct(t.pnl_pct)}</td>
                      <td className="num-cell">{fmtNum(t.pnl_points)}</td>
                      <td className="num-cell">{t.pnl_amount === null ? "—" : `₹${fmtNum(t.pnl_amount, 0)}`}</td>
                      <td className="num-cell">{t.holding_days ?? "—"}</td>
                      <td>{t.status}</td>
                    </tr>
                  ))}
                  {filteredTrades.length === 0 && (
                    <tr>
                      <td colSpan={16} style={{ textAlign: "center", padding: 16, opacity: 0.7 }}>
                        No trades match the current filters.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="card">
            <h2 style={{ marginTop: 0 }}>Equity Curve</h2>
            <EquityCurveChart points={result.equity_curve} />
          </div>
        </>
      )}
    </div>
  );
}

function SummaryTile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="tb-summary-tile">
      <div className="tb-summary-label">{label}</div>
      <div className="tb-summary-value">{value}</div>
    </div>
  );
}
