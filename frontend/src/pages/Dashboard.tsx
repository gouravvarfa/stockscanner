import { useState } from "react";
import { api, type StrategySignal } from "../services/api";
import { useScan } from "../context/ScanContext";
import { BestStockCard } from "../components/BestStockCard";
import { Badge } from "../components/Badge";

function fmtNum(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined || Number.isNaN(value) ? "N/A" : value.toFixed(digits);
}

const RSI_BY_TIMEFRAME_KEY = { DAILY: "daily_rsi", WEEKLY: "weekly_rsi", MONTHLY: "monthly_rsi" } as const;

function DivergenceSignalCard({ signal }: { signal: StrategySignal }) {
  const timeframes = (signal.extra.divergence_timeframes as string[] | undefined) ?? [];
  const rsiForTimeframe = (tf: string): number | null => {
    const key = RSI_BY_TIMEFRAME_KEY[tf as keyof typeof RSI_BY_TIMEFRAME_KEY];
    return key ? (signal[key] as number | null) : null;
  };
  const currentPrice = signal.extra.current_price as number | undefined;
  const dataSource = signal.extra.data_source as string | undefined;

  return (
    <div className="top3-item divergence-card">
      <div className="symbol">{signal.symbol}</div>
      <div className="muted small">{signal.sector}</div>
      <div className="chip">
        {signal.strategy} • {timeframes.join(" + ") || "—"}
      </div>
      <div className="small">
        {timeframes.map((tf) => (
          <div key={tf}>
            {tf} RSI: {fmtNum(rsiForTimeframe(tf))}
          </div>
        ))}
      </div>
      {currentPrice !== undefined && <div className="small">Price: {fmtNum(currentPrice, 2)}</div>}
      <div className="muted small">Signal: Confirmed</div>
      <div className="muted small">
        Date: {signal.signal_date ? new Date(signal.signal_date).toLocaleDateString() : "N/A"}
      </div>
      {dataSource && <div className="muted small">Source: {dataSource}</div>}
    </div>
  );
}

function DivergenceSignalsSection({ title, signals }: { title: string; signals: StrategySignal[] }) {
  return (
    <div className="card">
      <h3>
        {title} <span className="tab-count">{signals.length}</span>
      </h3>
      {signals.length === 0 ? (
        <p className="muted">No {title.toLowerCase()} in this scan.</p>
      ) : (
        <div className="top3-grid">
          {signals.map((s) => (
            <DivergenceSignalCard key={s.symbol} signal={s} />
          ))}
        </div>
      )}
    </div>
  );
}

export function Dashboard() {
  const { latest, setLatest } = useScan();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRunScan() {
    setLoading(true);
    setError(null);
    try {
      const result = await api.runScan("manual");
      setLatest(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>Dashboard</h1>
        <button className="primary-button" onClick={handleRunScan} disabled={loading}>
          {loading ? "Scanning NIFTY 200…" : "Run Scan"}
        </button>
      </div>

      {error && <div className="error-banner">Scan failed: {error}</div>}

      {latest && (
        <div className="scan-meta card">
          <div>
            Data as of <strong>{new Date(latest.finished_at).toLocaleString()}</strong>
          </div>
          <div>
            Universe: {latest.universe_returned}/{latest.universe_requested}{" "}
            {latest.universe_complete ? <Badge label="SECTOR OUTPERFORMING" /> : <span className="muted">(partial coverage)</span>}
          </div>
          <div>Stocks scanned: {latest.stocks_scanned} · failed: {latest.stocks_failed}</div>
          <div>Qualifying sectors: {latest.qualifying_sectors.join(", ") || "none"}</div>
          <div>Execution time: {latest.execution_seconds.toFixed(1)}s</div>
          {latest.universe_note && <div className="muted small">{latest.universe_note}</div>}
        </div>
      )}

      <BestStockCard stock={latest?.best ?? null} />

      {latest && latest.top3.length > 1 && (
        <div className="card">
          <h3>Top 3 Setups</h3>
          <div className="top3-grid">
            {latest.top3.map((s) => (
              <div key={s.symbol} className="top3-item">
                <div className="symbol">{s.symbol}</div>
                <div className="muted">{s.sector}</div>
                <div className="score">{s.score.toFixed(1)}</div>
                <Badge label={s.classification} />
              </div>
            ))}
          </div>
        </div>
      )}

      {latest && (
        <>
          <DivergenceSignalsSection title="PRD Signals" signals={latest.strategies?.["PRD"] ?? []} />
          <DivergenceSignalsSection title="NRD Signals" signals={latest.strategies?.["NRD"] ?? []} />
        </>
      )}
    </div>
  );
}
