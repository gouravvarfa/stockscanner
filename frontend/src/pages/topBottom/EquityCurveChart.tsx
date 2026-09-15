import { useEffect, useRef } from "react";
import { ColorType, createChart, LineSeries, type Time } from "lightweight-charts";
import type { EquityPoint } from "../../services/topBottomApi";

/**
 * lightweight-charts requires a strictly ascending, unique time axis.
 * Two equity points CAN legitimately land on the same bar — a reversal
 * exits one trade and the following trade can close on that very same bar
 * (e.g. the final END_OF_BACKTEST close). Keep the LAST value for such a
 * timestamp, which is the equity after both trades settled.
 */
function dedupeAscending(points: { time: number; value: number }[]) {
  const byTime = new Map<number, number>();
  for (const p of points) byTime.set(p.time, p.value);
  return Array.from(byTime.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([time, value]) => ({ time: time as Time, value }));
}

export function EquityCurveChart({ points }: { points: EquityPoint[] }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const isDark = document.documentElement.getAttribute("data-theme") === "dark"
      || (!document.documentElement.hasAttribute("data-theme") && window.matchMedia("(prefers-color-scheme: dark)").matches);
    const colors = isDark
      ? { bg: "#0f1115", text: "#c9ced6", grid: "#1d2129", equity: "#22c55e", dd: "#ef4444" }
      : { bg: "#ffffff", text: "#1a1d23", grid: "#eef0f3", equity: "#16a34a", dd: "#dc2626" };

    const chart = createChart(container, {
      layout: { background: { type: ColorType.Solid, color: colors.bg }, textColor: colors.text },
      grid: { vertLines: { color: colors.grid }, horzLines: { color: colors.grid } },
      timeScale: { timeVisible: true, borderColor: colors.grid },
      rightPriceScale: { borderColor: colors.grid },
      autoSize: true,
    });

    const equitySeries = chart.addSeries(LineSeries, { color: colors.equity, lineWidth: 2, title: "Equity" });
    const ddSeries = chart.addSeries(LineSeries, { color: colors.dd, lineWidth: 1, title: "Drawdown %" });

    const toTime = (iso: string) => Math.floor(new Date(iso).getTime() / 1000);

    equitySeries.setData(dedupeAscending(points.map((p) => ({ time: toTime(p.date), value: p.equity }))));
    ddSeries.setData(dedupeAscending(points.map((p) => ({ time: toTime(p.date), value: -p.drawdown_pct }))));

    if (points.length) chart.timeScale().fitContent();

    return () => chart.remove();
  }, [points]);

  return <div ref={containerRef} style={{ width: "100%", height: 260 }} />;
}
