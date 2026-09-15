import { useState } from "react";
import { api, type ExpiryLevel5Result, type ExpiryLevel5Signal } from "../services/api";
import { Badge } from "../components/Badge";
import { AngelOneStatusBanner } from "../components/AngelOneStatusBanner";
import { ConditionChip } from "../components/ConditionChip";

function fmt(value: number | null, digits = 2): string {
  return value === null || !Number.isFinite(value) ? "N/A" : value.toFixed(digits);
}

function SignalCard({ s }: { s: ExpiryLevel5Signal }) {
  return (
    <div className="card">
      <div className="best-stock-header">
        <div className="symbol">{s.symbol}</div>
        <Badge label="BULLISH" />
        <span className="chip chip-pass">{s.signal}</span>
        <span className="muted small" style={{ marginLeft: "auto" }}>
          {new Date(s.signal_date).toLocaleString()}
        </span>
      </div>

      <div className="best-stock-grid">
        <div>
          <span className="muted">Swing High</span>
          <br />
          {fmt(s.swing_high)}
        </div>
        <div>
          <span className="muted">Swing Low</span>
          <br />
          {fmt(s.swing_low)}
        </div>
        <div>
          <span className="muted">38.2%</span>
          <br />
          {fmt(s.fib_38_2)}
        </div>
        <div>
          <span className="muted">50%</span>
          <br />
          {fmt(s.fib_50)}
        </div>
        <div>
          <span className="muted">61.8% (support)</span>
          <br />
          {fmt(s.fib_61_8)}
        </div>
        <div>
          <span className="muted">Support Price</span>
          <br />
          {fmt(s.support_price)}
        </div>
        <div>
          <span className="muted">Confirmation Close</span>
          <br />
          {fmt(s.confirmation_candle.close)}
        </div>
        <div>
          <span className="muted">Previous Candle High</span>
          <br />
          {fmt(s.previous_candle_high)}
        </div>
      </div>

      <div className="chip-row" style={{ marginTop: 12 }}>
        <ConditionChip label="support confirmed" passed={s.support_confirmed} />
        <ConditionChip label="close above previous high" passed={s.confirmation_close_above_previous_high} />
      </div>

      <h4>Confirmation Candle</h4>
      <div className="best-stock-grid">
        <div>
          <span className="muted">Open</span>
          <br />
          {fmt(s.confirmation_candle.open)}
        </div>
        <div>
          <span className="muted">High</span>
          <br />
          {fmt(s.confirmation_candle.high)}
        </div>
        <div>
          <span className="muted">Low</span>
          <br />
          {fmt(s.confirmation_candle.low)}
        </div>
        <div>
          <span className="muted">Close</span>
          <br />
          {fmt(s.confirmation_candle.close)}
        </div>
      </div>

      <h4>Reason</h4>
      <p>{s.reason}</p>
      <p className="disclaimer">
        Underlying signal only — pick the actual CE contract on your broker/TradingView. Not financial advice.
      </p>
    </div>
  );
}

export function ExpiryLevel5() {
  const [result, setResult] = useState<ExpiryLevel5Result | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [angelOneConfigured, setAngelOneConfigured] = useState(false);

  async function handleRun() {
    setLoading(true);
    setError(null);
    try {
      const r = await api.runExpiryLevel5Scan();
      setResult(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Expiry Level 5</h1>
          <p className="page-subtitle">
            Stock futures taking support near the 61.8% Fibonacci retracement, confirmed by a candle closing above
            the previous candle's high. Signal: BUY CE (underlying only — you pick the option contract).
          </p>
        </div>
        <button className="primary-button" onClick={handleRun} disabled={loading || !angelOneConfigured}>
          {loading ? "Scanning…" : "Run Level 5 Scan"}
        </button>
      </div>

      <AngelOneStatusBanner onConnectedChange={setAngelOneConfigured} />

      {error && <div className="error-banner">Scan failed: {error}</div>}

      {result && !result.angelone_configured && (
        <div className="error-banner">
          Angel One is not connected — connect it above. Expiry Level 5 uses Angel One stock-future data only.
        </div>
      )}

      {result && result.angelone_configured && (
        <div className="card scan-meta">
          <div>
            Data as of <strong>{new Date(result.finished_at).toLocaleString()}</strong>
          </div>
          <div>
            Scanned: {result.symbols_scanned} · Failed: {result.symbols_failed} · Signals: {result.signals.length}
          </div>
          <div>Execution time: {result.execution_seconds.toFixed(1)}s</div>
          {result.failed_symbols.length > 0 && (
            <div className="muted small">Failed symbols: {result.failed_symbols.join(", ")}</div>
          )}
          {result.errors.length > 0 && (
            <div className="muted small">{result.errors.join(" · ")}</div>
          )}
        </div>
      )}

      {result && result.angelone_configured && (
        result.signals.length === 0 ? (
          <div className="card state-block">
            <div className="state-title">No signals found</div>
            <div className="state-subtitle">No BUY CE signals in this scan.</div>
          </div>
        ) : (
          result.signals.map((s) => <SignalCard key={s.symbol} s={s} />)
        )
      )}

      {!result && !error && <p className="muted">Run a scan to see current Expiry Level 5 signals.</p>}
    </div>
  );
}
