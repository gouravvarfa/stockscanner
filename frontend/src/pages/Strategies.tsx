import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, STRATEGY_NAMES, strategyDisplayName, type StrategyDescriptor } from "../services/api";
import { useScan } from "../context/ScanContext";
import { BacktestMotif, PageHero } from "../components/PageHero";

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
      <PageHero
        tone="backtest"
        eyebrow="Strategies · backtests"
        title="Backtesting"
        subtitle="Every strategy the scanner runs, how many stocks qualify today, and — for System One and the GFS family — a full backtest on past data."
        motif={<BacktestMotif />}
      >
        <span className="hero-pill">{STRATEGY_NAMES.length} strategies</span>
        <span className="hero-pill hero-pill-soft">Open a card to backtest it</span>
      </PageHero>

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
            const body = (
              <>
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
              </>
            );
            // System One, GFS, Advanced GFS and 50 GFS open their backtest pages; the other cards are info-only.
            const backtestRoute = name === "Strategy One" ? "/strategies/system-one" : name === "GFS" ? "/strategies/gfs" : name === "Advanced GFS" ? "/strategies/advanced-gfs" : name === "50 GFS" ? "/strategies/gfs-50" : null;
            return backtestRoute ? (
              <Link
                key={name}
                to={backtestRoute}
                className="strategy-card strategy-card-link"
                aria-label={`Open ${name === "Strategy One" ? "System One" : name} backtest`}
              >
                {body}
                <span className="strategy-card-cta">Open backtest →</span>
              </Link>
            ) : (
              <div key={name} className="strategy-card">
                {body}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
