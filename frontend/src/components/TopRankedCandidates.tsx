import { useEffect, useState } from "react";
import { rankingApi, type LatestRankingOut, type RankedCandidateOut } from "../services/rankingApi";
import { strategyDisplayName } from "../services/api";
import { InstrumentBadge } from "./InstrumentBadge";

/**
 * Reads the ranking the backend already computed from the last completed
 * scan (backend/ranking/engine.py, via GET /api/ranking/latest) — never
 * triggers a scan itself. Re-fetches whenever `refreshKey` changes (the
 * Dashboard bumps this after a scan finishes) so it stays in sync without
 * polling on its own.
 */
export function TopRankedCandidates({ refreshKey }: { refreshKey: unknown }) {
  const [data, setData] = useState<LatestRankingOut | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

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

  if (!data || data.top_candidates.length === 0) {
    return (
      <div className="card">
        <h2 style={{ marginTop: 0 }}>Top Ranked Candidates</h2>
        <p className="muted">None</p>
      </div>
    );
  }

  return (
    <div className="card ranked-panel">
      <div className="panel-head">
        <h2>Top Ranked Candidates</h2>
      </div>
      <p className="panel-sub">
        Ranked by setup strength, not a buy recommendation. Only stocks that actually qualified for at least
        one strategy appear here.
      </p>
      <div className="ranked-list">
        {data.top_candidates.map((c, i) => (
          <RankedRow
            key={c.symbol}
            rank={i + 1}
            candidate={c}
            expanded={expanded === c.symbol}
            onToggle={() => setExpanded((cur) => (cur === c.symbol ? null : c.symbol))}
          />
        ))}
      </div>
    </div>
  );
}

function RankedRow({
  rank,
  candidate,
  expanded,
  onToggle,
}: {
  rank: number;
  candidate: RankedCandidateOut;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="ranked-row" onClick={onToggle}>
      <div className="ranked-row-top">
        <span className="ranked-rank">#{rank}</span>
        <span className="ranked-symbol">{candidate.symbol}<InstrumentBadge type={candidate.instrument_type} /></span>
        <span className="ranked-score">{candidate.score.toFixed(1)}</span>
      </div>
      <div className="ranked-strategies">
        {candidate.strategies.map((s) => (
          <span key={s} className="chip chip-pass" style={{ marginRight: 4 }}>
            {strategyDisplayName(s)}
          </span>
        ))}
      </div>
      {expanded && (
        <div className="ranked-explanation">
          {Object.entries(candidate.strategy_breakdown).map(([strategy, breakdown]) => (
            <div key={strategy} style={{ marginBottom: 8 }}>
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
        </div>
      )}
    </div>
  );
}
