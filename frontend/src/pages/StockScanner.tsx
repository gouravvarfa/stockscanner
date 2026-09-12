import { useEffect, useMemo, useState } from "react";
import { useScan } from "../context/ScanContext";
import { STRATEGY_NAMES, strategyDisplayName, type NiftyUniverseStock } from "../services/api";
import { SourceBadge } from "../components/SourceBadge";

type SortKey = "symbol" | "sector" | "current_price" | "daily_rsi" | "weekly_rsi" | "monthly_rsi";
const PAGE_SIZE = 50;

function fmt(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined || Number.isNaN(value) ? "—" : value.toFixed(digits);
}

function fmtPrice(value: number | null | undefined): string {
  return value === null || value === undefined || Number.isNaN(value) ? "—" : `₹${value.toFixed(2)}`;
}

export function StockScanner() {
  const { latest } = useScan();
  const [sortKey, setSortKey] = useState<SortKey>("symbol");
  const [asc, setAsc] = useState(true);
  const [sectorFilter, setSectorFilter] = useState<string>("all");
  const [strategyFilter, setStrategyFilter] = useState<string>("all");
  const [sourceFilter, setSourceFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [symbolSearch, setSymbolSearch] = useState("");
  const [page, setPage] = useState(1);

  const universe = latest?.nifty200_universe ?? [];

  // Which strategies each symbol currently qualifies for — derived purely
  // from already-loaded scan data, no extra lookups/calls.
  const strategiesBySymbol = useMemo(() => {
    const map = new Map<string, string[]>();
    if (!latest) return map;
    for (const name of STRATEGY_NAMES) {
      for (const sig of latest.strategies?.[name] ?? []) {
        const list = map.get(sig.symbol) ?? [];
        list.push(name);
        map.set(sig.symbol, list);
      }
    }
    return map;
  }, [latest]);

  const sectors = useMemo(() => {
    const set = new Set(universe.map((s) => s.sector).filter(Boolean));
    return ["all", ...Array.from(set).sort()];
  }, [universe]);

  const sources = useMemo(() => {
    const set = new Set(universe.map((s) => s.data_source).filter((v): v is string => !!v));
    return ["all", ...Array.from(set).sort()];
  }, [universe]);

  useEffect(() => setPage(1), [sectorFilter, strategyFilter, sourceFilter, statusFilter, symbolSearch]);

  const filtered = useMemo(() => {
    let rows = universe;
    if (sectorFilter !== "all") rows = rows.filter((s) => s.sector === sectorFilter);
    if (sourceFilter !== "all") rows = rows.filter((s) => s.data_source === sourceFilter);
    if (statusFilter !== "all") rows = rows.filter((s) => s.status === statusFilter);
    if (strategyFilter !== "all") {
      rows = rows.filter((s) => (strategiesBySymbol.get(s.symbol) ?? []).includes(strategyFilter));
    }
    if (symbolSearch.trim()) {
      const q = symbolSearch.trim().toUpperCase();
      rows = rows.filter((s) => s.symbol.toUpperCase().includes(q));
    }

    const sorted = [...rows];
    sorted.sort((a, b) => {
      let av: number | string;
      let bv: number | string;
      if (sortKey === "symbol" || sortKey === "sector") {
        av = a[sortKey];
        bv = b[sortKey];
        return asc ? av.localeCompare(bv) : bv.localeCompare(av);
      }
      if (sortKey === "current_price") {
        av = a.current_price ?? -Infinity;
        bv = b.current_price ?? -Infinity;
      } else {
        const key = sortKey === "daily_rsi" ? "daily_rsi" : sortKey === "weekly_rsi" ? "weekly_rsi" : "monthly_rsi";
        av = a[key] ?? -Infinity;
        bv = b[key] ?? -Infinity;
      }
      return asc ? (av as number) - (bv as number) : (bv as number) - (av as number);
    });
    return sorted;
  }, [universe, sectorFilter, sourceFilter, statusFilter, strategyFilter, symbolSearch, strategiesBySymbol, sortKey, asc]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pageRows = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  function sortBy(key: SortKey) {
    if (key === sortKey) setAsc(!asc);
    else {
      setSortKey(key);
      setAsc(true);
    }
  }

  if (!latest) {
    return (
      <div className="page">
        <div className="page-header">
          <div>
            <h1>NIFTY 200 Scanner</h1>
            <p className="page-subtitle">Full universe with sector, price, RSI, and strategy signals</p>
          </div>
        </div>
        <div className="card state-block">
          <div className="state-title">No signals found</div>
          <div className="state-subtitle">Run a scan from the Dashboard to see the NIFTY 200 universe.</div>
        </div>
      </div>
    );
  }

  const incomplete = latest.universe_returned < latest.universe_requested;

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>NIFTY 200 Scanner</h1>
          <p className="page-subtitle">
            Showing {universe.length} of {latest.universe_requested} NIFTY 200 stocks
          </p>
        </div>
      </div>

      {incomplete && (
        <div className="card state-block warning-block">
          <div className="state-title">DATA INCOMPLETE</div>
          <div className="state-subtitle">
            The authoritative universe source returned {latest.universe_returned} of {latest.universe_requested}{" "}
            constituents this scan{latest.universe_note ? ` — ${latest.universe_note}` : ""}. No stocks were
            invented to fill the gap.
          </div>
        </div>
      )}

      <div className="card filters-row">
        <label>
          Search symbol
          <input type="text" value={symbolSearch} onChange={(e) => setSymbolSearch(e.target.value)} placeholder="e.g. RELIANCE" />
        </label>
        <label>
          Sector
          <select value={sectorFilter} onChange={(e) => setSectorFilter(e.target.value)}>
            {sectors.map((s) => (
              <option key={s} value={s}>
                {s === "all" ? "All Sectors" : s}
              </option>
            ))}
          </select>
        </label>
        <label>
          Strategy
          <select value={strategyFilter} onChange={(e) => setStrategyFilter(e.target.value)}>
            <option value="all">All Strategies</option>
            {STRATEGY_NAMES.map((name) => (
              <option key={name} value={name}>
                {strategyDisplayName(name)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Data Source
          <select value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)}>
            {sources.map((s) => (
              <option key={s} value={s}>
                {s === "all" ? "All Sources" : s}
              </option>
            ))}
          </select>
        </label>
        <label>
          Status
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="all">All Statuses</option>
            <option value="OK">OK</option>
            <option value="DATA_UNAVAILABLE">Data Unavailable</option>
          </select>
        </label>
      </div>

      {universe.length === 0 ? (
        <div className="card state-block">
          <div className="state-title">No signals found</div>
          <div className="state-subtitle">The universe provider returned no constituents for this scan.</div>
        </div>
      ) : filtered.length === 0 ? (
        <div className="card state-block">
          <div className="state-title">No signals found</div>
          <div className="state-subtitle">No stocks match the current filters.</div>
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th onClick={() => sortBy("symbol")}>Symbol</th>
                <th>Company</th>
                <th onClick={() => sortBy("sector")}>Sector</th>
                <th onClick={() => sortBy("current_price")} className="num-cell">Price</th>
                <th onClick={() => sortBy("daily_rsi")} className="num-cell">Daily RSI</th>
                <th onClick={() => sortBy("weekly_rsi")} className="num-cell">Weekly RSI</th>
                <th onClick={() => sortBy("monthly_rsi")} className="num-cell">Monthly RSI</th>
                <th>Signal</th>
                <th>Data Source</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map((s: NiftyUniverseStock) => {
                const strategies = strategiesBySymbol.get(s.symbol) ?? [];
                const unavailable = s.status !== "OK";
                return (
                  <tr key={s.symbol} className={unavailable ? "row-unavailable" : undefined}>
                    <td className="symbol-cell">{s.symbol}</td>
                    <td>{s.company_name ?? "—"}</td>
                    <td>{s.sector}</td>
                    <td className="num-cell">{fmtPrice(s.current_price)}</td>
                    <td className="num-cell">{fmt(s.daily_rsi)}</td>
                    <td className="num-cell">{fmt(s.weekly_rsi)}</td>
                    <td className="num-cell">{fmt(s.monthly_rsi)}</td>
                    <td>
                      {strategies.length > 0 ? (
                        <div className="chip-row">
                          {strategies.map((name) => (
                            <span key={name} className="chip chip-pass">
                              {strategyDisplayName(name)}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <span className="muted small">—</span>
                      )}
                    </td>
                    <td>
                      <SourceBadge source={s.data_source} />
                    </td>
                    <td title={s.status_reason ?? undefined}>
                      {s.status === "OK" ? (
                        <span className="chip chip-pass">OK</span>
                      ) : (
                        <span className="chip chip-fail">DATA UNAVAILABLE</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="table-pagination">
            <span>
              Showing {(currentPage - 1) * PAGE_SIZE + 1}–{Math.min(currentPage * PAGE_SIZE, filtered.length)} of{" "}
              {filtered.length} stocks
            </span>
            <div className="pagination-controls">
              <button disabled={currentPage === 1} onClick={() => setPage(currentPage - 1)}>
                Previous
              </button>
              {Array.from({ length: totalPages }, (_, i) => i + 1)
                .slice(Math.max(0, currentPage - 3), Math.max(0, currentPage - 3) + 5)
                .map((p) => (
                  <button key={p} className={p === currentPage ? "active" : ""} onClick={() => setPage(p)}>
                    {p}
                  </button>
                ))}
              <button disabled={currentPage === totalPages} onClick={() => setPage(currentPage + 1)}>
                Next
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
