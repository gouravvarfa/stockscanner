import { InstrumentBadge } from "../components/InstrumentBadge";
import { PageHero, TopBottomMotif } from "../components/PageHero";
import { StockLogo } from "../components/StockLogo";
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
      <PageHero
        tone="topbottom"
        eyebrow="Backtest · tops and bottoms"
        title="Top Bottom Backtesting"
        subtitle="An always-in-the-market system: it trails a stop under each bottom and over each top, and reverses on a close beyond it."
        motif={<TopBottomMotif />}
      >
        <span className="hero-pill">Close-price tops and bottoms</span>
        <span className="hero-pill hero-pill-soft">Stop and reverse · always in the market</span>
      </PageHero>

      <div className="card tb-config-card">
        <div className="tb-card-head">
          <span className="tb-step">1</span>
          <div>
            <h2>Backtest setup</h2>
            <p className="muted small">Pick the market, the stock or contract, the period and the candle size — then run.</p>
          </div>
        </div>
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
                <option value="FUTURES">Futures (NSE + SENSEX + MCX Gold/Silver)</option>
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
              {contract.commodity ? ` · Commodity Future · ₹${contract.point_value ?? 0} per point per lot` : contract.is_index ? " · Index Future" : " · Stock Future"}
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

          <div className="card tb-result-card">
            <div className="tb-card-head">
              <span className="tb-step">2</span>
              <div className="tb-result-title">
                <h2>
                  <span className="logo-line"><span className="wk-logo"><StockLogo symbol={result.symbol} /></span>{result.symbol}</span>
                  <InstrumentBadge type={result.instrument_type} />
                </h2>
                <p className="muted small">
                  {fmtDate(result.coverage.available_from)} – {fmtDate(result.coverage.available_to)} · {result.statistics.total_signals} trades
                  ({result.statistics.buy_signals} buy · {result.statistics.sell_signals} sell)
                </p>
              </div>
            </div>
            <div className="tb-kpis">
              <Kpi label="Net P&L" value={fmtPct(result.statistics.net_pnl_pct)} tone={toneOf(result.statistics.net_pnl_pct)} big />
              <Kpi label="Win rate" value={fmtPct(result.statistics.win_rate)} hint={`${result.statistics.winning_trades} won · ${result.statistics.losing_trades} lost`} big />
              <Kpi label="Profit factor" value={result.statistics.profit_factor === null ? "N/A" : fmtNum(result.statistics.profit_factor)}
                tone={result.statistics.profit_factor === null ? undefined : result.statistics.profit_factor >= 1 ? "up" : "down"} hint="gross profit ÷ gross loss" big />
              <Kpi label="Max drawdown" value={fmtPct(result.statistics.max_drawdown_pct)} tone="down" hint="worst fall from a peak" big />
            </div>
            <div className="tb-kpis tb-kpis-small">
              <Kpi label="Average trade" value={fmtPct(result.statistics.average_trade_pct)} tone={toneOf(result.statistics.average_trade_pct)} />
              <Kpi label="Best trade" value={fmtPct(result.statistics.best_trade_pct)} tone="up" />
              <Kpi label="Worst trade" value={fmtPct(result.statistics.worst_trade_pct)} tone="down" />
              <Kpi label="Avg holding" value={`${fmtNum(result.statistics.average_holding_days, 1)} days`} />
            </div>
          </div>

          <div className="card">
            <div className="tb-card-head"><span className="tb-step">3</span><div><h2>Price and signals</h2><p className="muted small">Click a trade in the table to highlight it on the chart.</p></div></div>
            <TopBottomChart result={result} focusedTradeNumber={focusedTrade} />
          </div>

          <div className="card">
            <div className="tb-card-head"><span className="tb-step">4</span><div><h2>Trades</h2><p className="muted small">Every entry and exit, newest at the bottom.</p></div></div>
            <div className="filters-row tb-filters">
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
              {filtersActive && <span className="tb-filter-note">Showing {filteredTrades.length} of {result.trades.length} trades</span>}
            </div>

            <div className="table-wrap">
              <table className="tb-trades">
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
                      <td><span className={`tb-dir ${t.direction === "BUY" ? "tb-dir-buy" : "tb-dir-sell"}`}>{t.direction}</span></td>
                      <td className="num-cell">{fmtNum(t.system_point)}</td>
                      <td className="num-cell">{fmtNum(t.entry_price)}</td>
                      <td className="num-cell">{fmtNum(t.initial_sl)}</td>
                      <td className="num-cell">{fmtNum(t.active_stop)}</td>
                      <td className="num-cell">{fmtNum(t.exit_price)}</td>
                      <td>{fmtDate(t.exit_date)}</td>
                      <td className="muted small">{t.exit_reason ? t.exit_reason.replace(/_/g, " ").toLowerCase().replace(/^./, (c) => c.toUpperCase()) : "—"}</td>
                      <td className={`num-cell ${pnlClass(t.pnl_pct)}`}><b>{fmtPct(t.pnl_pct)}</b></td>
                      <td className={`num-cell ${pnlClass(t.pnl_points)}`}>{fmtNum(t.pnl_points)}</td>
                      <td className={`num-cell ${pnlClass(t.pnl_amount)}`}>{t.pnl_amount === null ? "—" : `${t.pnl_amount < 0 ? "-" : ""}₹${fmtNum(Math.abs(t.pnl_amount), 0)}`}</td>
                      <td className="num-cell">{t.holding_days ?? "—"}</td>
                      <td><span className={`tb-status tb-status-${String(t.status).toLowerCase()}`}>{t.status}</span></td>
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
            <div className="tb-card-head"><span className="tb-step">5</span><div><h2>Equity curve</h2><p className="muted small">How the account would have grown, trade by trade.</p></div></div>
            <EquityCurveChart points={result.equity_curve} />
          </div>
        </>
      )}
    </div>
  );
}

const toneOf = (v: number | null | undefined): "up" | "down" | undefined => (v == null ? undefined : v >= 0 ? "up" : "down");
const pnlClass = (v: number | null | undefined) => (v == null ? "" : v > 0 ? "wk-up" : v < 0 ? "wk-down" : "");

function Kpi({ label, value, hint, tone, big }: { label: string; value: string | number; hint?: string; tone?: "up" | "down"; big?: boolean }) {
  return (
    <div className={`tb-kpi${big ? " tb-kpi-big" : ""}${tone ? ` tb-kpi-${tone}` : ""}`}>
      <div className="tb-kpi-label">{label}</div>
      <div className="tb-kpi-value">{value}</div>
      {hint && <div className="tb-kpi-hint">{hint}</div>}
    </div>
  );
}
