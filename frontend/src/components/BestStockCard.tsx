import type { StockResult } from "../services/api";
import { Badge } from "./Badge";

export function BestStockCard({ stock }: { stock: StockResult | null }) {
  if (!stock) {
    return (
      <div className="card best-stock-card empty">
        <h2>Best Stock Setup</h2>
        <p className="muted">Run a scan to identify the highest-ranked setup.</p>
      </div>
    );
  }

  return (
    <div className="card best-stock-card">
      <div className="best-stock-header">
        <h2>Best Stock Setup</h2>
        <span className="chip" style={{ marginLeft: 4 }}>System One</span>
        <Badge label={stock.classification} />
        <Badge label={stock.bias} />
      </div>
      <p className="muted small" style={{ marginTop: -8, marginBottom: 14 }}>
        This is the top pick from System One only. GFS, Advanced GFS, PRD, NRD, and Value Buy each have their
        own separate results — see the Strategies page.
      </p>
      <div className="best-stock-main">
        <div>
          <div className="symbol">{stock.symbol}</div>
        </div>
        <div className="price">₹{stock.current_price.toFixed(2)}</div>
        <div className="score">{stock.score.toFixed(1)}<span className="muted">/100</span></div>
      </div>

      <div className="best-stock-grid">
        <div><span className="muted">Daily RSI</span><br />{stock.daily.rsi?.toFixed(1) ?? "—"}</div>
        <div><span className="muted">Weekly RSI</span><br />{stock.weekly.rsi?.toFixed(1) ?? "—"}</div>
        <div><span className="muted">Monthly RSI</span><br />{stock.monthly.rsi?.toFixed(1) ?? "—"}</div>
        <div>
          <span className="muted">Divergence</span><br />
          <Badge label={stock.weekly.has_bearish_divergence || stock.monthly.has_bearish_divergence ? "BEARISH DIVERGENCE" : "NO DIVERGENCE"} />
        </div>
        <div>
          <span className="muted">Fibonacci Zone</span><br />
          {stock.fibonacci ? `${stock.fibonacci.nearest_ratio} (${stock.fibonacci.distance_pct.toFixed(1)}%)` : "—"}
        </div>
        <div><span className="muted">Volume Ratio</span><br />{stock.volume_ratio?.toFixed(2) ?? "—"}x</div>
      </div>

      <div className="explanation">
        <h4>Why this stock qualifies</h4>
        <ul>
          {stock.explanation.map((line, i) => (
            <li key={i}>{line}</li>
          ))}
        </ul>
        {stock.data_warnings.length > 0 && (
          <div className="warnings">
            {stock.data_warnings.map((w, i) => (
              <div key={i} className="warning-line">⚠ {w}</div>
            ))}
          </div>
        )}
        <p className="disclaimer">
          Highest-ranked setup according to the defined strategy — not a guarantee of future performance.
          This is not financial advice.
        </p>
      </div>

      {stock.trade_setup && (
        <div className="trade-setup">
          <h4>Trade Setup</h4>
          {stock.trade_setup.available ? (
            <div className="trade-setup-grid">
              <div><span className="muted">Entry</span><br />₹{stock.trade_setup.entry_low?.toFixed(2)} – ₹{stock.trade_setup.entry_high?.toFixed(2)}</div>
              <div><span className="muted">Stop Loss</span><br />₹{stock.trade_setup.stop_loss?.toFixed(2)}</div>
              <div><span className="muted">Target 1</span><br />₹{stock.trade_setup.target1?.toFixed(2)}</div>
              <div><span className="muted">Target 2</span><br />₹{stock.trade_setup.target2?.toFixed(2)}</div>
              <div><span className="muted">R:R (T1/T2)</span><br />{stock.trade_setup.risk_reward_t1 ?? "—"} / {stock.trade_setup.risk_reward_t2 ?? "—"}</div>
              <div className="methodology muted">{stock.trade_setup.methodology}</div>
            </div>
          ) : (
            <p className="muted">{stock.trade_setup.reason}</p>
          )}
        </div>
      )}
    </div>
  );
}
