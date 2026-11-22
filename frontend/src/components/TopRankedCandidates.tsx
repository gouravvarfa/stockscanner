import { Fragment, useEffect, useState } from "react";
import { useChart } from "../chart/ChartContext";
import { rankingApi, type LatestRankingOut, type RankedCandidateOut } from "../services/rankingApi";
import { strategyDisplayName } from "../services/api";
import { InstrumentBadge } from "./InstrumentBadge";
import { StockLogo } from "./StockLogo";
import { TrendIcon } from "./icons";

/**
 * Reads the ranking the backend already computed from the last completed
 * scan (backend/ranking/engine.py, via GET /api/ranking/latest) — never
 * triggers a scan itself. Re-fetches whenever `refreshKey` changes (the
 * Dashboard bumps this after a scan finishes) so it stays in sync without
 * polling on its own. Shown as a compact table (2026-11-22): click a row for the score breakdown.
 */
export function TopRankedCandidates({ refreshKey }: { refreshKey: unknown }) {
  const [data, setData] = useState<LatestRankingOut | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const { openChart } = useChart();

  useEffect(() => {
    let cancelled = false;
    rankingApi
      .latest()
      .then((r) => {
        if (!cancelled) setData(r);
      })
      .catch(() => {
        if (!cancelled) setData(null);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  const chart = (c: RankedCandidateOut) =>
    openChart(c.symbol, {
      strategy: c.strategies.map(strategyDisplayName).join(" + "),
      daily_rsi: null,
      weekly_rsi: null,
      monthly_rsi: null,
      signal_date: null,
      explanation: `Ranked by setup strength: ${c.score.toFixed(1)}.`,
      indicators: { rsi: true, volume: true, bollinger: true },
    });

  return (
    <section className="card" aria-labelledby="dash-ranked-title">
      <div className="dash-card-head">
        <div>
          <h2 id="dash-ranked-title">Top ranked candidates</h2>
          <p className="muted small">
            Ranked by setup strength across every setup, not a buy recommendation. Click a row for the score breakdown.
          </p>
        </div>
      </div>
      {!data || data.top_candidates.length === 0 ? (
        <p className="muted" style={{ marginBottom: 0 }}>None</p>
      ) : (
        <div className="table-wrap">
          <table className="wk-table dash-rank-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Stock</th>
                <th>Setups</th>
                <th>Score</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.top_candidates.map((c, i) => (
                <Fragment key={c.symbol}>
                  <tr className="wk-click" onClick={() => setExpanded((cur) => (cur === c.symbol ? null : c.symbol))}>
                    <td className="muted">{i + 1}</td>
                    <td>
                      <div className="dash-stock">
                        <span className="wk-logo">
                          <StockLogo symbol={c.symbol} />
                        </span>
                        <span className="dash-stock-sym">
                          {c.symbol}
                          <InstrumentBadge type={c.instrument_type} />
                        </span>
                      </div>
                    </td>
                    <td>
                      <div className="dash-setups">
                        {c.strategies.map((s) => (
                          <span key={s} className="chip chip-pass">{strategyDisplayName(s)}</span>
                        ))}
                      </div>
                    </td>
                    <td className="dash-score">{c.score.toFixed(1)}</td>
                    <td>
                      <button
                        type="button"
                        className="wk-chart-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          chart(c);
                        }}
                        aria-label={`Open the ${c.symbol} chart`}
                      >
                        <TrendIcon width={13} height={13} aria-hidden="true" />
                        Chart
                      </button>
                    </td>
                  </tr>
                  {expanded === c.symbol && (
                    <tr className="dash-rank-detail">
                      <td />
                      <td colSpan={4}>
                        {Object.entries(c.strategy_breakdown).map(([strategy, breakdown]) => (
                          <div key={strategy} style={{ marginBottom: 6 }}>
                            <strong>{strategyDisplayName(strategy)}</strong>
                            {breakdown.strength !== null && <span> — {breakdown.strength.toFixed(1)}</span>}
                            <div className="ranked-components">
                              {Object.entries(breakdown.components).map(([comp, val]) => (
                                <span key={comp} className="ranked-component">
                                  {comp.replace(/_/g, " ")}: <b>{val === null ? "N/A" : val.toFixed(1)}</b>
                                </span>
                              ))}
                            </div>
                          </div>
                        ))}
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
