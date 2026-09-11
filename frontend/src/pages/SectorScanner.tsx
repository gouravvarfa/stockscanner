import { useMemo, useState } from "react";
import { useScan } from "../context/ScanContext";
import type { SectorResult } from "../services/api";
import { Badge } from "../components/Badge";

type SortKey = keyof Pick<
  SectorResult,
  "sector" | "daily_return_pct" | "weekly_return_pct" | "monthly_return_pct" | "daily_rsi" | "weekly_rsi" | "monthly_rsi" | "sector_score"
>;

export function SectorScanner() {
  const { latest } = useScan();
  const [sortKey, setSortKey] = useState<SortKey>("sector_score");
  const [asc, setAsc] = useState(false);

  const sectors = useMemo(() => {
    if (!latest) return [];
    const rows = [...latest.sectors];
    rows.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (av === null && bv === null) return 0;
      if (av === null) return 1;
      if (bv === null) return -1;
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
        <h1>Sector Scanner</h1>
        <p className="muted">Run a scan from the Dashboard to see sector data.</p>
      </div>
    );
  }

  return (
    <div className="page">
      <h1>Sector Scanner</h1>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th onClick={() => sortBy("sector")}>Sector</th>
              <th onClick={() => sortBy("daily_return_pct")}>Daily Return</th>
              <th onClick={() => sortBy("weekly_return_pct")}>Weekly Return</th>
              <th onClick={() => sortBy("monthly_return_pct")}>Monthly Return</th>
              <th>D vs NIFTY</th>
              <th>W vs NIFTY</th>
              <th>M vs NIFTY</th>
              <th onClick={() => sortBy("daily_rsi")}>Daily RSI</th>
              <th onClick={() => sortBy("weekly_rsi")}>Weekly RSI</th>
              <th onClick={() => sortBy("monthly_rsi")}>Monthly RSI</th>
              <th onClick={() => sortBy("sector_score")}>Score</th>
            </tr>
          </thead>
          <tbody>
            {sectors.map((s) => {
              const qualifies = latest.qualifying_sectors.includes(s.sector);
              return (
                <tr key={s.sector} className={qualifies ? "row-highlight" : ""}>
                  <td>{s.sector}{!s.available && <span className="muted small"> (unavailable)</span>}</td>
                  <td>{s.daily_return_pct?.toFixed(2) ?? "—"}%</td>
                  <td>{s.weekly_return_pct?.toFixed(2) ?? "—"}%</td>
                  <td>{s.monthly_return_pct?.toFixed(2) ?? "—"}%</td>
                  <td>{s.daily_vs_nifty?.toFixed(2) ?? "—"}</td>
                  <td>{s.weekly_vs_nifty?.toFixed(2) ?? "—"}</td>
                  <td>{s.monthly_vs_nifty?.toFixed(2) ?? "—"}</td>
                  <td>{s.daily_rsi?.toFixed(1) ?? "—"}</td>
                  <td>{s.weekly_rsi?.toFixed(1) ?? "—"}</td>
                  <td>{s.monthly_rsi?.toFixed(1) ?? "—"}</td>
                  <td>{s.sector_score.toFixed(1)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="legend">
        {latest.qualifying_sectors.map((s) => (
          <Badge key={s} label="SECTOR OUTPERFORMING" />
        ))}
      </div>
    </div>
  );
}
