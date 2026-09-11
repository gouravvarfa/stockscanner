import { useEffect, useState } from "react";
import { api, type ScanRunSummary } from "../services/api";

export function ScanHistoryPage() {
  const [runs, setRuns] = useState<ScanRunSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .listHistory(50)
      .then(setRuns)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="page">
      <h1>Scan History</h1>
      {loading && <p className="muted">Loading…</p>}
      {error && <div className="error-banner">{error}</div>}
      {!loading && runs.length === 0 && <p className="muted">No scans have been run yet.</p>}
      {runs.length > 0 && (
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
              {runs.map((r) => (
                <tr key={r.id}>
                  <td>{r.id}</td>
                  <td>{r.scan_type}</td>
                  <td>{new Date(r.started_at).toLocaleString()}</td>
                  <td>{r.execution_seconds?.toFixed(1) ?? "—"}s</td>
                  <td>
                    {r.universe_returned}/{r.universe_requested} {r.universe_complete ? "✓" : "(partial)"}
                  </td>
                  <td>{r.stocks_scanned}</td>
                  <td>{r.stocks_failed}</td>
                  <td>{r.qualifying_sectors}</td>
                  <td>{r.qualifying_stocks}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
