import { useEffect, useState } from "react";
import { api, STRATEGY_NAMES, strategyDisplayName, type StrategyDescriptor } from "../services/api";
import { useScan } from "../context/ScanContext";

export function Strategies() {
  const { latest } = useScan();
  const [descriptors, setDescriptors] = useState<StrategyDescriptor[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .listStrategies()
      .then(setDescriptors)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Strategies</h1>
          <p className="page-subtitle">Active strategy definitions and current signal counts</p>
        </div>
      </div>

      {error && <div className="error-banner small">Could not load strategy descriptions: {error}</div>}

      {loading ? (
        <div className="strategy-grid">
          {STRATEGY_NAMES.map((name) => (
            <div key={name} className="strategy-card">
              <div className="skeleton-bar" style={{ width: "50%", height: 16 }} />
              <div className="skeleton-bar" style={{ width: "100%" }} />
              <div className="skeleton-bar" style={{ width: "80%" }} />
            </div>
          ))}
        </div>
      ) : (
        <div className="strategy-grid">
          {STRATEGY_NAMES.map((name) => {
            const descriptor = descriptors.find((d) => d.name === name);
            const count = latest?.strategies?.[name]?.length;
            return (
              <div key={name} className="strategy-card">
                <div className="strategy-card-top">
                  <span className="strategy-card-name">{strategyDisplayName(name)}</span>
                </div>
                <p className="strategy-card-desc">{descriptor?.description ?? "No description available."}</p>
                <div className="strategy-card-footer">
                  <span className="strategy-status">
                    <span className="dot" /> Active
                  </span>
                  <span className="strategy-signal-count">
                    {latest ? (
                      <>
                        <b>{count ?? 0}</b> qualifying
                      </>
                    ) : (
                      "Run a scan"
                    )}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
