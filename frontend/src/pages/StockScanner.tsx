import { useMemo, useState } from "react";
import { useScan } from "../context/ScanContext";
import type { StockResult } from "../services/api";
import { Badge } from "../components/Badge";

type SortKey = "symbol" | "sector" | "current_price" | "score";

export function StockScanner() {
  const { latest } = useScan();
  const [sortKey, setSortKey] = useState<SortKey>("score");
  const [asc, setAsc] = useState(false);

  const stocks = useMemo(() => {
    if (!latest) return [] as StockResult[];
    const rows = [...latest.top10];
    rows.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (typeof av === "string") return asc ? av.localeCompare(bv as string) : (bv as string).localeCompare(av);
      return asc ? (av as number) - (bv as number) : (bv as number) - (av as number);
    });
    return rows;
  }, [latest, sortKey, asc]);

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
        <h1>NIFTY 200 Stock Scanner</h1>
        <p className="muted">Run a scan from the Dashboard to see stock setups.</p>
      </div>
    );
  }

  return (
    <div className="page">
      <h1>NIFTY 200 Stock Scanner</h1>
      <p className="muted">Showing qualifying candidates from the strongest sectors (Top 10, ranked by score).</p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Rank</th>
              <th onClick={() => sortBy("symbol")}>Symbol</th>
              <th onClick={() => sortBy("sector")}>Sector</th>
              <th onClick={() => sortBy("current_price")}>Price</th>
              <th>Daily RSI</th>
              <th>Weekly RSI</th>
              <th>Monthly RSI</th>
              <th>Divergence (D/W/M)</th>
              <th>Fib Zone</th>
              <th>20/50/200 EMA</th>
              <th>MACD</th>
              <th>ADX</th>
              <th>Vol Ratio</th>
              <th>52W High Dist</th>
              <th onClick={() => sortBy("score")}>Score</th>
              <th>Setup</th>
            </tr>
          </thead>
          <tbody>
            {stocks.map((s) => (
              <tr key={s.symbol}>
                <td>{s.rank}</td>
                <td>{s.symbol}</td>
                <td>{s.sector}</td>
                <td>₹{s.current_price.toFixed(2)}</td>
                <td>{s.daily.rsi?.toFixed(1) ?? "—"}</td>
                <td>{s.weekly.rsi?.toFixed(1) ?? "—"}</td>
                <td>{s.monthly.rsi?.toFixed(1) ?? "—"}</td>
                <td>
                  {s.daily.has_bearish_divergence ? "🔻" : "—"}/
                  {s.weekly.has_bearish_divergence ? "🔻" : "—"}/
                  {s.monthly.has_bearish_divergence ? "🔻" : "—"}
                </td>
                <td>{s.fibonacci ? `${s.fibonacci.nearest_ratio}` : "—"}</td>
                <td>
                  {s.ema20?.toFixed(0) ?? "—"}/{s.ema50?.toFixed(0) ?? "—"}/{s.ema200?.toFixed(0) ?? "—"}
                </td>
                <td>{s.macd_histogram?.toFixed(2) ?? "—"}</td>
                <td>{s.adx?.toFixed(1) ?? "—"}</td>
                <td>{s.volume_ratio?.toFixed(2) ?? "—"}</td>
                <td>{s.distance_from_52w_high_pct?.toFixed(1) ?? "—"}%</td>
                <td>{s.score.toFixed(1)}</td>
                <td><Badge label={s.classification} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
