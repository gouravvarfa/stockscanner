import { useEffect, useMemo, useState } from "react";
import { api, STRATEGY_NAMES, type StockResult, type StrategyDescriptor, type StrategyName, type StrategySignal } from "../services/api";
import { useScan } from "../context/ScanContext";
import { StockDetailPanel } from "../components/StockDetailPanel";
import { ConditionChip } from "../components/ConditionChip";

type SortKey = "symbol" | "sector" | "daily_rsi" | "weekly_rsi" | "monthly_rsi" | "score";

function fmt(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined || Number.isNaN(value) ? "N/A" : value.toFixed(digits);
}

export function Strategies() {
  const { latest } = useScan();
  const [descriptors, setDescriptors] = useState<StrategyDescriptor[]>([]);
  const [descError, setDescError] = useState<string | null>(null);
  const [activeStrategy, setActiveStrategy] = useState<StrategyName>("Strategy One");
  const [sortKey, setSortKey] = useState<SortKey>("score");
  const [asc, setAsc] = useState(false);
  const [sectorFilter, setSectorFilter] = useState<string>("all");
  const [symbolSearch, setSymbolSearch] = useState("");
  const [rsiMin, setRsiMin] = useState<string>("");
  const [rsiMax, setRsiMax] = useState<string>("");
  const [selected, setSelected] = useState<StrategySignal | null>(null);

  useEffect(() => {
    api
      .listStrategies()
      .then(setDescriptors)
      .catch((e) => setDescError(e instanceof Error ? e.message : String(e)));
  }, []);

  const signalsForActive: StrategySignal[] = latest?.strategies?.[activeStrategy] ?? [];

  const richBySymbol = useMemo(() => {
    const map = new Map<string, StockResult>();
    for (const r of latest?.top10 ?? []) map.set(r.symbol, r);
    return map;
  }, [latest]);

  const sectors = useMemo(() => {
    const set = new Set(signalsForActive.map((s) => s.sector));
    return ["all", ...Array.from(set).sort()];
  }, [signalsForActive]);

  const filtered = useMemo(() => {
    let rows = signalsForActive;
    if (sectorFilter !== "all") rows = rows.filter((s) => s.sector === sectorFilter);
    if (symbolSearch.trim()) {
      const q = symbolSearch.trim().toUpperCase();
      rows = rows.filter((s) => s.symbol.toUpperCase().includes(q));
    }
    const min = rsiMin === "" ? null : Number(rsiMin);
    const max = rsiMax === "" ? null : Number(rsiMax);
    if (min !== null) rows = rows.filter((s) => s.daily_rsi !== null && s.daily_rsi >= min);
    if (max !== null) rows = rows.filter((s) => s.daily_rsi !== null && s.daily_rsi <= max);

    const sorted = [...rows];
    sorted.sort((a, b) => {
      let av: number | string;
      let bv: number | string;
      if (sortKey === "symbol" || sortKey === "sector") {
        av = a[sortKey];
        bv = b[sortKey];
        return asc ? (av as string).localeCompare(bv as string) : (bv as string).localeCompare(av as string);
      }
      if (sortKey === "score") {
        av = (a.extra.score as number | undefined) ?? -Infinity;
        bv = (b.extra.score as number | undefined) ?? -Infinity;
      } else {
        av = a[sortKey] ?? -Infinity;
        bv = b[sortKey] ?? -Infinity;
      }
      return asc ? (av as number) - (bv as number) : (bv as number) - (av as number);
    });
    return sorted;
  }, [signalsForActive, sectorFilter, symbolSearch, rsiMin, rsiMax, sortKey, asc]);

  function sortBy(key: SortKey) {
    if (key === sortKey) setAsc(!asc);
    else {
      setSortKey(key);
      setAsc(false);
    }
  }

  if (!latest) {
    return (
      <div className="page">
        <h1>Strategies</h1>
        <p className="muted">Run a scan from the Dashboard to see strategy recommendations.</p>
      </div>
    );
  }

  return (
    <div className="page">
      <h1>Strategies</h1>
      {descError && <div className="error-banner small">Could not load strategy descriptions: {descError}</div>}

      <div className="tabs">
        {STRATEGY_NAMES.map((name) => {
          const count = latest.strategies?.[name]?.length ?? 0;
          return (
            <button
              key={name}
              className={activeStrategy === name ? "tab active" : "tab"}
              onClick={() => setActiveStrategy(name)}
            >
              {name} <span className="tab-count">{count}</span>
            </button>
          );
        })}
      </div>

      <div className="card">
        <p className="muted">
          {descriptors.find((d) => d.name === activeStrategy)?.description ?? ""}
        </p>
        <p>
          <strong>{filtered.length}</strong> of <strong>{signalsForActive.length}</strong> qualifying stocks shown.
        </p>
      </div>

      <div className="card filters-row">
        <label>
          Sector
          <select value={sectorFilter} onChange={(e) => setSectorFilter(e.target.value)}>
            {sectors.map((s) => (
              <option key={s} value={s}>
                {s === "all" ? "All sectors" : s}
              </option>
            ))}
          </select>
        </label>
        <label>
          Search symbol
          <input type="text" value={symbolSearch} onChange={(e) => setSymbolSearch(e.target.value)} placeholder="e.g. RELIANCE" />
        </label>
        <label>
          Daily RSI min
          <input type="number" value={rsiMin} onChange={(e) => setRsiMin(e.target.value)} />
        </label>
        <label>
          Daily RSI max
          <input type="number" value={rsiMax} onChange={(e) => setRsiMax(e.target.value)} />
        </label>
      </div>

      {signalsForActive.length === 0 ? (
        <div className="card">
          <p className="muted">No stocks currently qualify for {activeStrategy} in this scan.</p>
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th onClick={() => sortBy("symbol")}>Symbol</th>
                <th onClick={() => sortBy("sector")}>Sector</th>
                <th>Signal Date</th>
                <th onClick={() => sortBy("daily_rsi")}>Daily RSI</th>
                <th onClick={() => sortBy("weekly_rsi")}>Weekly RSI</th>
                <th onClick={() => sortBy("monthly_rsi")}>Monthly RSI</th>
                {activeStrategy === "Strategy One" && <th onClick={() => sortBy("score")}>Score</th>}
                {activeStrategy === "Value Buy" && <th>Conditions</th>}
                {(activeStrategy === "PRD" || activeStrategy === "NRD") && <th>Divergence</th>}
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((s) => (
                <tr key={s.symbol} onClick={() => setSelected(s)} className="clickable-row">
                  <td>{s.symbol}</td>
                  <td>{s.sector}</td>
                  <td>{s.signal_date ? new Date(s.signal_date).toLocaleDateString() : "N/A"}</td>
                  <td>{fmt(s.daily_rsi)}</td>
                  <td>{fmt(s.weekly_rsi)}</td>
                  <td>{fmt(s.monthly_rsi)}</td>
                  {activeStrategy === "Strategy One" && <td>{fmt(s.extra.score as number | undefined)}</td>}
                  {activeStrategy === "Value Buy" && (
                    <td>
                      <div className="chip-row">
                        {Object.entries(s.conditions).map(([k, v]) => (
                          <ConditionChip key={k} label={k} passed={v} />
                        ))}
                      </div>
                    </td>
                  )}
                  {(activeStrategy === "PRD" || activeStrategy === "NRD") && (
                    <td>
                      {Array.isArray(s.extra.divergence_timeframes) && s.extra.divergence_timeframes.length > 0
                        ? `${activeStrategy} — ${(s.extra.divergence_timeframes as string[]).join(" + ")}`
                        : "—"}
                    </td>
                  )}
                  <td className="explanation-cell">{s.explanation}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selected && (
        <StockDetailPanel signal={selected} richData={richBySymbol.get(selected.symbol) ?? null} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
