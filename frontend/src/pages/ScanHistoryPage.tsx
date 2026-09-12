import { useEffect, useState } from "react";
import { api, type ScanRunSummary } from "../services/api";

export function ScanHistoryPage() {
  const [runs, setRuns] = useState<ScanRunSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  function load() {
    setLoading(true);
    setError(null);
    api
      .listHistory(50)
      .then(setRuns)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Scan History</h1>
          <p className="page-subtitle">Past scan runs and their coverage</p>
        </div>
      </div>

      {error && (
        <div className="error-banner">
          <div>
            <strong>Unable to load scanner data.</strong> {error}
          </div>
          <button className="secondary-button" onClick={load}>
            Retry
          </button>
        </div>
      )}

      {!loading && !error && runs.length === 0 && (
        <div className="card state-block">
          <div className="state-title">No signals found</div>
          <div className="state-subtitle">No scans have been run yet.</div>
        </div>
      )}

      {(loading || runs.length > 0) && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Type</th>
                <th>Started</th>
                <th>Duration</th>
                <th>Universe</th>
                <th>Scanned</th>
                <th>Failed</th>
                <th>Qualifying Sectors</th>
                <th>Qualifying Stocks</th>
              </tr>
            </thead>
            <tbody>
              {loading
                ? [0, 1, 2, 3, 4].map((row) => (
                    <tr key={row} className="skeleton-row">
                      {Array.from({ length: 9 }).map((_, col) => (
                        <td key={col}>
                          <div className="skeleton-bar" style={{ width: col === 0 ? "40%" : "60%" }} />
                        </td>
                      ))}
                    </tr>
                  ))
                : runs.map((r) => (
                    <tr key={r.id}>
                      <td className="num-cell">{r.id}</td>
                      <td>{r.scan_type}</td>
                      <td>{new Date(r.started_at).toLocaleString()}</td>
                      <td className="num-cell">{r.execution_seconds?.toFixed(1) ?? "—"}s</td>
                      <td>
                        {r.universe_returned}/{r.universe_requested} {r.universe_complete ? "✓" : "(partial)"}
                      </td>
                      <td className="num-cell">{r.stocks_scanned}</td>
                      <td className="num-cell">{r.stocks_failed}</td>
                      <td className="num-cell">{r.qualifying_sectors}</td>
                      <td className="num-cell">{r.qualifying_stocks}</td>
                    </tr>
                  ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
