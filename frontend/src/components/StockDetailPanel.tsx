import type { StockResult, StrategySignal } from "../services/api";
import { Badge } from "./Badge";
import { ConditionChip } from "./ConditionChip";

function fmt(value: number | null | undefined, digits = 2, suffix = ""): string {
  return value === null || value === undefined || Number.isNaN(value) ? "N/A" : `${value.toFixed(digits)}${suffix}`;
}

function renderDivergenceExtra(extra: Record<string, unknown>) {
  const divergences = extra["divergences"];
  if (!Array.isArray(divergences) || divergences.length === 0) {
    return <p className="muted">No confirmed divergence to display.</p>;
  }
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Timeframe</th>
            <th>Swing 1</th>
            <th>Swing 2</th>
            <th>RSI 1 → RSI 2</th>
            <th>Price Δ%</th>
            <th>RSI Δ</th>
          </tr>
        </thead>
        <tbody>
          {divergences.map((d, i) => {
            const row = d as Record<string, unknown>;
            return (
              <tr key={i}>
                <td>{String(row.timeframe)}</td>
                <td>
                  {row.swing1_date ? new Date(String(row.swing1_date)).toLocaleDateString() : "N/A"} @{" "}
                  {fmt(row.swing1_price as number)}
                </td>
                <td>
                  {row.swing2_date ? new Date(String(row.swing2_date)).toLocaleDateString() : "N/A"} @{" "}
                  {fmt(row.swing2_price as number)}
                </td>
                <td>
                  {fmt(row.rsi1 as number, 1)} → {fmt(row.rsi2 as number, 1)}
                </td>
                <td>{fmt(row.price_change_pct as number, 2, "%")}</td>
                <td>{fmt(row.rsi_change as number, 1)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function renderValueBuyExtra(extra: Record<string, unknown>) {
  return (
    <div className="best-stock-grid">
      <div>
        <span className="muted">Key Reversal</span>
        <br />
        {extra.key_reversal_detected ? "YES" : "No"}
      </div>
      <div>
        <span className="muted">Trendline Breakout</span>
        <br />
        {extra.trendline_breakout_detected ? "YES" : "No"}
      </div>
      <div>
        <span className="muted">Breakout Price</span>
        <br />
        {fmt(extra.trendline_breakout_price as number)}
      </div>
      <div>
        <span className="muted">Trendline Price at Breakout</span>
        <br />
        {fmt(extra.trendline_price_at_breakout as number)}
      </div>
    </div>
  );
}

export function StockDetailPanel({
  signal,
  richData,
  onClose,
}: {
  signal: StrategySignal;
  richData: StockResult | null;
  onClose: () => void;
}) {
  return (
    <div className="detail-overlay" onClick={onClose}>
      <div className="detail-panel card" onClick={(e) => e.stopPropagation()}>
        <div className="detail-header">
          <div>
            <div className="symbol">{signal.symbol}</div>
            <div className="muted">
              {signal.sector} · {signal.strategy}
            </div>
          </div>
          <button className="secondary-button" onClick={onClose}>
            Close
          </button>
        </div>

        <h4>Signal</h4>
        <div className="best-stock-grid">
          <div>
            <span className="muted">Signal Date</span>
            <br />
            {signal.signal_date ? new Date(signal.signal_date).toLocaleDateString() : "N/A"}
          </div>
          <div>
            <span className="muted">Daily RSI</span>
            <br />
            {fmt(signal.daily_rsi, 1)}
          </div>
          <div>
            <span className="muted">Weekly RSI</span>
            <br />
            {fmt(signal.weekly_rsi, 1)}
          </div>
          <div>
            <span className="muted">Monthly RSI</span>
            <br />
            {fmt(signal.monthly_rsi, 1)}
          </div>
          {richData && (
            <>
              <div>
                <span className="muted">Price</span>
                <br />
                ₹{fmt(richData.current_price)}
              </div>
              {typeof signal.extra.score === "number" && (
                <div>
                  <span className="muted">Score</span>
                  <br />
                  {fmt(signal.extra.score as number, 1)}
                </div>
              )}
            </>
          )}
        </div>

        <h4>Conditions</h4>
        <div className="chip-row">
          {Object.entries(signal.conditions).map(([key, passed]) => (
            <ConditionChip key={key} label={key} passed={passed} />
          ))}
        </div>

        {(signal.strategy === "PRD" || signal.strategy === "NRD") && (
          <>
            <h4>{signal.strategy === "PRD" ? "Positive Reverse Divergence" : "Negative Reverse Divergence"}</h4>
            {renderDivergenceExtra(signal.extra)}
          </>
        )}

        {signal.strategy === "Value Buy" && (
          <>
            <h4>Value Buy Trigger</h4>
            {renderValueBuyExtra(signal.extra)}
          </>
        )}

        <h4>Explanation</h4>
        <p>{signal.explanation}</p>

        <h4>Trend / Momentum / Volume</h4>
        {richData ? (
          <div className="best-stock-grid">
            <div>
              <span className="muted">EMA 20/50/200</span>
              <br />
              {fmt(richData.ema20, 1)} / {fmt(richData.ema50, 1)} / {fmt(richData.ema200, 1)}
            </div>
            <div>
              <span className="muted">MACD Histogram</span>
              <br />
              {fmt(richData.macd_histogram)}
            </div>
            <div>
              <span className="muted">ADX</span>
              <br />
              {fmt(richData.adx, 1)}
            </div>
            <div>
              <span className="muted">Volume Ratio</span>
              <br />
              {fmt(richData.volume_ratio)}x
            </div>
            <div>
              <span className="muted">52-Week High Distance</span>
              <br />
              {fmt(richData.distance_from_52w_high_pct, 1, "%")}
            </div>
            {richData.fibonacci && (
              <div>
                <span className="muted">Nearest Fibonacci Level</span>
                <br />
                {richData.fibonacci.nearest_ratio} ({fmt(richData.fibonacci.distance_pct, 2, "%")})
              </div>
            )}
          </div>
        ) : (
          <p className="muted">
            Not available — detailed trend/momentum/volume/Fibonacci data is only computed for Strategy One's
            Top 10 in this scan. This stock qualified for {signal.strategy} but wasn't in that set.
          </p>
        )}

        {richData?.trade_setup?.available && (
          <>
            <h4>Reference Levels</h4>
            <div className="trade-setup-grid">
              <div>
                <span className="muted">Entry</span>
                <br />
                ₹{fmt(richData.trade_setup.entry_low)} – ₹{fmt(richData.trade_setup.entry_high)}
              </div>
              <div>
                <span className="muted">Stop Loss</span>
                <br />
                ₹{fmt(richData.trade_setup.stop_loss)}
              </div>
              <div>
                <span className="muted">Target 1 / 2</span>
                <br />
                ₹{fmt(richData.trade_setup.target1)} / ₹{fmt(richData.trade_setup.target2)}
              </div>
            </div>
          </>
        )}

        {richData && <Badge label={richData.classification} />}
      </div>
    </div>
  );
}
