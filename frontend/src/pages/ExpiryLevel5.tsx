import { useState } from "react";
import type { ExpiryLevel5Result, ExpiryLevel5Signal } from "../services/api";
import { Badge } from "../components/Badge";
import { InstrumentBadge } from "../components/InstrumentBadge";
import { AngelOneStatusBanner } from "../components/AngelOneStatusBanner";
import { ConditionChip } from "../components/ConditionChip";
import { useScanJob } from "../hooks/useScanJob";

function fmt(value: number | null, digits = 2): string {
  return value === null || !Number.isFinite(value) ? "N/A" : value.toFixed(digits);
}

function SignalCard({ s }: { s: ExpiryLevel5Signal }) {
  return (
    <div className="card">
      <div className="best-stock-header">
        <div className="symbol">{s.symbol}<InstrumentBadge type={s.fno_type} /></div>
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
  const { result, running, error, cache, run, runFresh } = useScanJob<ExpiryLevel5Result>("expiry_level_5");
  const [angelOneConfigured, setAngelOneConfigured] = useState(false);

  const cacheAgeSeconds = cache ? (Date.now() - new Date(cache.completed_at).getTime()) / 1000 : null;

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
        <div style={{ display: "flex", gap: 10 }}>
          <button className="primary-button" onClick={run} disabled={running || !angelOneConfigured}>
            {running ? "Scanning…" : "Run Level 5 Scan"}
          </button>
          {!running && (
            <button className="secondary-button" onClick={runFresh} disabled={!angelOneConfigured} title="Ignore cache, fetch fresh data">
              Fresh Scan
            </button>
          )}
        </div>
      </div>

      <AngelOneStatusBanner onConnectedChange={setAngelOneConfigured} />

      {!running && cacheAgeSeconds !== null && (
        <p style={{ fontSize: 12, opacity: 0.7 }}>
          Cached data — age {Math.floor(cacheAgeSeconds / 3600)}h {Math.floor((cacheAgeSeconds % 3600) / 60)}m
        </p>
      )}

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
