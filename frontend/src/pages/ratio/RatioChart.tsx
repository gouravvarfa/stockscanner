import { useEffect, useRef } from "react";
import { createChart, LineSeries, LineStyle, type UTCTimestamp } from "lightweight-charts";
import type { Pt } from "./ratioMath";

/** The ratio line with today's zones: high (85th pct), median, low (15th pct). Colours follow the app theme. */
export function RatioChart({ data, low, high, median, ma }: { data: Pt[]; low: number; high: number; median: number; ma: Pt[] }) {
  const el = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!el.current) return;
    const css = getComputedStyle(document.documentElement);
    const v = (name: string, fb: string) => css.getPropertyValue(name).trim() || fb;
    const text = v("--text-secondary", "#64748b"), grid = v("--border", "#e2e8f0"), line = v("--pt", "#155e75");
    const chart = createChart(el.current, {
      autoSize: true,
      layout: { background: { color: "transparent" }, textColor: text, fontFamily: "inherit" },
      grid: { vertLines: { visible: false }, horzLines: { color: grid } },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false },
      crosshair: { mode: 1 },
      handleScroll: true, handleScale: true,
    });
    const fmt = (p: number) => (p >= 100 ? p.toFixed(0) : p >= 1 ? p.toFixed(3) : p.toFixed(4));
    const s = chart.addSeries(LineSeries, { color: line, lineWidth: 2, priceFormat: { type: "custom", formatter: fmt, minMove: 0.0001 }, lastValueVisible: true, priceLineVisible: false });
    s.setData(data.map(([t, val]) => ({ time: t as UTCTimestamp, value: val })));
    const avg = chart.addSeries(LineSeries, { color: v("--text-muted", "#94a3b8"), lineWidth: 1, lineStyle: LineStyle.Dotted, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false });
    avg.setData(ma.map(([t, val]) => ({ time: t as UTCTimestamp, value: val })));
    s.createPriceLine({ price: high, color: "#ea580c", lineWidth: 2, lineStyle: LineStyle.Solid, axisLabelVisible: true, title: "High zone" });
    s.createPriceLine({ price: median, color: v("--text-muted", "#94a3b8"), lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false, title: "Median" });
    s.createPriceLine({ price: low, color: "#16a34a", lineWidth: 2, lineStyle: LineStyle.Solid, axisLabelVisible: true, title: "Low zone" });
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [data, low, high, median, ma]);
  return <div ref={el} className="rt-chart" />;
}
