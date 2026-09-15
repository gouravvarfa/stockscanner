import { useState } from "react";
import { api, type ExpiryLevel1Result, type ExpiryLevel1Signal } from "../services/api";
import { Badge } from "../components/Badge";
import { AngelOneStatusBanner } from "../components/AngelOneStatusBanner";

type Section = "index" | "stock";

function fmt(value: number, digits = 1): string {
  return Number.isFinite(value) ? value.toFixed(digits) : "N/A";
}

function SignalTable({ rows }: { rows: ExpiryLevel1Signal[] }) {
  if (rows.length === 0) {
    return (
      <div className="card state-block">
        <div className="state-title">No signals found</div>
        <div className="state-subtitle">No confirmed signals in this scan.</div>
      </div>
    );
  }
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Type</th>
            <th>Signal Time</th>
            <th>15m RSI</th>
            <th>Previous 15m RSI</th>
            <th>1H RSI</th>
            <th>Status</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.symbol}-${r.signal_date}`} className="row-highlight">
              <td>{r.symbol}</td>
              <td>{r.instrument_type}</td>
              <td>{new Date(r.signal_date).toLocaleString()}</td>
              <td>{fmt(r.rsi_15m)}</td>
              <td>{fmt(r.rsi_15m_prev)}</td>
              <td>{fmt(r.rsi_1h)}</td>
              <td>
                <Badge label="BULLISH" />
                <span style={{ marginLeft: 6 }}>{r.status}</span>
              </td>
              <td className="explanation-cell">{r.explanation}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ExpiryLevel1() {
  const [result, setResult] = useState<ExpiryLevel1Result | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [section, setSection] = useState<Section>("index");
  const [angelOneConfigured, setAngelOneConfigured] = useState(false);

  async function handleRun() {
    setLoading(true);
    setError(null);
    try {
      const r = await api.runExpiryScan();
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
          <h1>Expiry Level 1</h1>
          <p className="page-subtitle">
            15-minute RSI between 58 and 65, with 1-hour RSI above 65. Underlying signal only — you
            choose the option contract on TradingView/your broker separately.
          </p>
        </div>
        <button className="primary-button" onClick={handleRun} disabled={loading || !angelOneConfigured}>
          {loading ? "Scanning…" : "Run Expiry Scan"}
        </button>
      </div>

      <AngelOneStatusBanner onConnectedChange={setAngelOneConfigured} />

      {error && <div className="error-banner">Scan failed: {error}</div>}

      {result && !result.angelone_configured && (
        <div className="error-banner">
          Angel One is not connected — connect it above. Expiry Level 1 needs intraday data that only Angel One
          provides in this project (Tapetide has daily bars only).
        </div>
      )}

      {result && result.angelone_configured && (
        <div className="card scan-meta">
          <div>
            Data as of <strong>{new Date(result.finished_at).toLocaleString()}</strong>
          </div>
          <div>
            Scanned: {result.symbols_scanned} · Failed: {result.symbols_failed}
          </div>
          <div>Execution time: {result.execution_seconds.toFixed(1)}s</div>
          {result.failed_symbols.length > 0 && (
            <div className="muted small">Failed symbols: {result.failed_symbols.join(", ")}</div>
          )}
        </div>
      )}

      {result && result.angelone_configured && (
        <>
          <div className="tabs">
            <button className={section === "index" ? "tab active" : "tab"} onClick={() => setSection("index")}>
              Index Signals <span className="tab-count">{result.index_signals.length}</span>
            </button>
            <button className={section === "stock" ? "tab active" : "tab"} onClick={() => setSection("stock")}>
              Stock Signals <span className="tab-count">{result.stock_signals.length}</span>
            </button>
          </div>
          <SignalTable rows={section === "index" ? result.index_signals : result.stock_signals} />
        </>
      )}

      {!result && !error && <p className="muted">Run a scan to see current Expiry Level 1 signals.</p>}
    </div>
  );
}
