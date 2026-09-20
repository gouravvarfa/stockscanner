import { useState } from "react";
import type { ExpiryLevel1Result, ExpiryLevel1Signal } from "../services/api";
import { Badge } from "../components/Badge";
import { InstrumentBadge } from "../components/InstrumentBadge";
import { AngelOneStatusBanner } from "../components/AngelOneStatusBanner";
import { useScanJob } from "../hooks/useScanJob";

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
            <th>Cross Status</th>
            <th>Status</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.symbol}-${r.signal_date}`} className="row-highlight">
              <td>{r.symbol}<InstrumentBadge type={r.fno_type} /></td>
              <td>{r.instrument_type}</td>
              <td>{new Date(r.signal_date).toLocaleString()}</td>
              <td>{fmt(r.rsi_15m)}</td>
              <td>{fmt(r.rsi_15m_prev)}</td>
              <td>{fmt(r.rsi_1h)}</td>
              <td>{r.cross_status.replace(/_/g, " ")}</td>
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
  const { result, running, error, cache, run, runFresh } = useScanJob<ExpiryLevel1Result>("expiry_level_1");
  const [section, setSection] = useState<Section>("index");
  const [angelOneConfigured, setAngelOneConfigured] = useState(false);

  const cacheAgeSeconds = cache ? (Date.now() - new Date(cache.completed_at).getTime()) / 1000 : null;

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Expiry Level 1</h1>
          <p className="page-subtitle">
            First confirmed 15-minute close above RSI 60, with 1-hour RSI above 65. Underlying signal
            only — you choose the option contract on TradingView/your broker separately.
          </p>
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          <button className="primary-button" onClick={run} disabled={running || !angelOneConfigured}>
            {running ? "Scanning…" : "Run Expiry Scan"}
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
