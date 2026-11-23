import { useMemo, useState } from "react";
import { useChart } from "../../chart/ChartContext";
import { StockLogo } from "../../components/StockLogo";

/**
 * Monthly RSI support (2026-11-23): every NSE stock whose monthly RSI sits in the 38-45 zone around 40 (the first Value
 * Buy rule alone, like a Chartink "monthly RSI near 40" screen), with the daily pullback inside the last up-swing. A
 * stock whose deepest pullback reached the 78.6% Fibonacci zone (74-82%) without breaking the swing low gets the
 * 78% tag - the user's PFC / REC setup.
 */
export type Retracement = {
  pct: number; deepest_pct: number; swing_high: number; swing_high_date: string; swing_low: number; swing_low_date: string;
  level_786: number; fib78: boolean;
};
export type SupportRow = {
  symbol: string; company_name: string; price: number; daily_rsi: number | null; weekly_rsi: number | null; monthly_rsi: number | null;
  conditions: Record<string, boolean>; value_buy: boolean; retracement: Retracement | null;
  month_open?: number; month_change_pct?: number;
};

const num = (v: number | null | undefined, d = 1) => (v == null ? "—" : v.toFixed(d));
const dmy = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "2-digit", month: "short" });

export function SupportZoneCard({ rows, strongMap, strongOnly, query }: {
  rows: SupportRow[]; strongMap: Record<string, string>; strongOnly: boolean; query: string;
}) {
  const { openChart } = useChart();
  const [only78, setOnly78] = useState(true);
  const list = useMemo(() => {
    const q = query.trim().toUpperCase();
    return rows
      .filter((r) => (!strongOnly || strongMap[r.symbol]) && (!only78 || r.retracement?.fib78) && (!q || r.symbol.includes(q)))
      .sort((a, b) => Number(!!b.retracement?.fib78) - Number(!!a.retracement?.fib78) || (a.monthly_rsi ?? 99) - (b.monthly_rsi ?? 99));
  }, [rows, strongMap, strongOnly, only78, query]);
  const count78 = rows.filter((r) => (!strongOnly || strongMap[r.symbol]) && r.retracement?.fib78).length;

  return (
    <>
      <div className="sz-bar">
        <label className="sz-only">
          <input type="checkbox" checked={only78} onChange={(e) => setOnly78(e.target.checked)} />
          Only the 78% pullback <b>{count78}</b>
        </label>
        <span className="muted small">Monthly RSI 38–45 with this month's candle (support at 40), and this month's candle green · daily pullback measured on the last swing low → high (5-day swings)</span>
      </div>
      {list.length === 0 ? (
        <p className="muted" style={{ marginBottom: 0 }}>{only78 ? "No stock with a 78% pullback in this list right now — untick to see every support-zone stock." : "No stock matches."}</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Stock</th>
                <th className="num-cell">Price</th>
                <th className="num-cell" title="Including this month's candle as of the data date">Monthly RSI (this month)</th>
                <th className="num-cell">Daily pullback</th>
                <th>Swing (low → high)</th>
                <th>Also</th>
              </tr>
            </thead>
            <tbody>
              {list.map((r) => {
                const ret = r.retracement;
                return (
                  <tr key={r.symbol} className="wk-click" onClick={() => openChart(r.symbol, { strategy: "Value Buy", monthly_rsi: r.monthly_rsi, daily_rsi: r.daily_rsi, weekly_rsi: r.weekly_rsi, signal_date: null, indicators: { rsi: true }, fibonacci: r.retracement ? { low: r.retracement.swing_low, high: r.retracement.swing_high } : null })}>
                    <td>
                      <span className="logo-line">
                        <span className="wk-logo"><StockLogo symbol={r.symbol} /></span>
                        <span className="dash-two"><b>{r.symbol}</b><small>{r.company_name}</small></span>
                        {strongMap[r.symbol] && <span className="vb-sector">{strongMap[r.symbol]}</span>}
                      </span>
                    </td>
                    <td className="num-cell">₹{num(r.price, 2)}</td>
                    <td className="num-cell">
                      <span className="sz-pull">
                        <b>{num(r.monthly_rsi)}</b>
                        {r.month_change_pct != null && <small className="wk-up">month +{num(r.month_change_pct)}%</small>}
                      </span>
                    </td>
                    <td className="num-cell">
                      {ret ? (
                        <span className="sz-pull">
                          {ret.fib78 && <span className="sz-78">78%</span>}
                          <span>{num(ret.deepest_pct, 0)}% deepest</span>
                          <small className="muted">now {num(ret.pct, 0)}% · 0.786 at ₹{num(ret.level_786, 2)}</small>
                        </span>
                      ) : "—"}
                    </td>
                    <td className="muted small">{ret ? `₹${num(ret.swing_low, 2)} (${dmy(ret.swing_low_date)}) → ₹${num(ret.swing_high, 2)} (${dmy(ret.swing_high_date)})` : "—"}</td>
                    <td>
                      {r.value_buy ? <span className="chip chip-pass">Value Buy</span> : (
                        <span className="muted small">
                          {r.conditions.latest_confirmed_weekly_candle_green ? "weekly green" : "weekly not green"} · {r.conditions.daily_key_reversal ? "key reversal" : "no key reversal"}
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
