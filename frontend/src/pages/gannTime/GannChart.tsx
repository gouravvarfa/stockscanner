import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  HistogramSeries,
  LineSeries,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import type { GannStockDetail } from "../../services/gannTimeApi";

const dayTs = (iso: string) => (Math.floor(Date.parse(`${iso}T00:00:00Z`) / 1000) as UTCTimestamp);

function isDark(): boolean {
  const el = document.documentElement;
  return el.getAttribute("data-theme") === "dark"
    || (!el.hasAttribute("data-theme") && window.matchMedia("(prefers-color-scheme: dark)").matches);
}

/** Candles + swing zigzag + red bands on cluster windows (±3 candles), drawn
 *  into the future on blank trading days so the dates sit on the time axis. */
export function GannChart({ data }: { data: GannStockDetail }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const dark = isDark();
    const c = dark
      ? { bg: "#0f1115", text: "#c9ced6", grid: "#1d2129", swing: "#4da3ff", band: "rgba(239,68,68,0.22)", soft: "rgba(239,68,68,0.10)" }
      : { bg: "#ffffff", text: "#1a1d23", grid: "#eef0f3", swing: "#2563eb", band: "rgba(220,38,38,0.18)", soft: "rgba(220,38,38,0.08)" };

    const chart = createChart(el, {
      layout: { background: { type: ColorType.Solid, color: c.bg }, textColor: c.text },
      grid: { vertLines: { color: c.grid }, horzLines: { color: c.grid } },
      timeScale: { borderColor: c.grid, rightOffset: 4 },
      rightPriceScale: { borderColor: c.grid },
      autoSize: true,
    });

    // Normalise candles to the date (midnight UTC) so they line up with the future dates.
    const candles = data.candles.map((k) => ({
      time: dayTs(new Date(k.time * 1000 + 6 * 3600 * 1000).toISOString().slice(0, 10)),
      open: k.open, high: k.high, low: k.low, close: k.close,
    }));
    const lastTs = candles[candles.length - 1]?.time ?? 0;

    // Future trading days: every projection date after the last candle, plus the gaps between.
    const futureDates = new Set<number>();
    data.projections.forEach((p) => { const t = dayTs(p.date); if (t > lastTs) futureDates.add(t); });
    const maxFuture = Math.max(lastTs, ...futureDates);
    for (let t = lastTs + 86400; t <= maxFuture; t += 86400) {
      const wd = new Date(t * 1000).getUTCDay();
      if (wd !== 0 && wd !== 6) futureDates.add(t);
    }
    const allTimes = [...candles.map((k) => k.time as number), ...[...futureDates].sort((a, b) => a - b)];

    // Cluster windows: ±3 trading candles around each cluster date.
    const bandColor = new Map<number, string>();
    data.clusters.forEach((cl) => {
      const i = allTimes.indexOf(dayTs(cl.date));
      if (i < 0) return;
      for (let j = Math.max(0, i - 3); j <= Math.min(allTimes.length - 1, i + 3); j++) {
        bandColor.set(allTimes[j], j === i ? c.band : bandColor.get(allTimes[j]) ?? c.soft);
      }
    });
    const bands = chart.addSeries(HistogramSeries, { priceScaleId: "bands", lastValueVisible: false, priceLineVisible: false });
    chart.priceScale("bands").applyOptions({ scaleMargins: { top: 0, bottom: 0 }, visible: false });
    bands.setData(allTimes.map((t) => (bandColor.has(t) ? { time: t as Time, value: 1, color: bandColor.get(t) } : { time: t as Time })));

    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#16a34a", downColor: "#dc2626", wickUpColor: "#16a34a", wickDownColor: "#dc2626", borderVisible: false,
    });
    series.setData([...candles, ...[...futureDates].sort((a, b) => a - b).map((t) => ({ time: t as Time }))]);

    const swing = chart.addSeries(LineSeries, { color: c.swing, lineWidth: 2, lastValueVisible: false, priceLineVisible: false });
    swing.setData(data.pivots.map((p) => ({ time: dayTs(p.date), value: p.price })));
    createSeriesMarkers(series, data.pivots.map((p) => ({
      time: dayTs(p.date),
      position: p.kind === "H" ? "aboveBar" as const : "belowBar" as const,
      color: c.swing,
      shape: "circle" as const,
      text: `${p.kind} ${Math.round(p.price)}`,
    })));

    // Angle halving fan from the last big swing's start: one straight line per angle,
    // origin -> last bar on the axis (lines run per candle, so future blank bars count).
    const fan = data.angles;
    if (fan) {
      const palette = dark
        ? ["#60a5fa", "#a78bfa", "#f472b6", "#fbbf24", "#2dd4bf", "#a3e635", "#94a3b8"]
        : ["#1d4ed8", "#7c3aed", "#be185d", "#d97706", "#0d9488", "#65a30d", "#475569"];
      const lastCandle = candles.length - 1;
      const oTs = dayTs(fan.origin_date);
      let o = allTimes.indexOf(oTs);
      if (o < 0) o = 0; // swing start older than the drawn candles: begin at the first candle
      const end = allTimes.length - 1;
      fan.lines.forEach((l) => {
        const at = (bar: number) => l.today + l.slope * (bar - lastCandle);
        const color = palette[Math.min(palette.length - 1, Math.round(Math.log2(1 / Math.abs(l.fraction || 1 / 64))))];
        const s = chart.addSeries(LineSeries, {
          color, lineWidth: 1, lineStyle: l.fraction < 0 ? 2 : l.fraction === 0 ? 1 : 0,
          lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false,
          autoscaleInfoProvider: () => null,
        });
        s.setData([{ time: allTimes[o] as Time, value: at(o) }, { time: allTimes[end] as Time, value: at(end) }]);
      });
    }

    // Show ~the last 9 months plus every future projection date (fitContent ignores blank future bars).
    chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, candles.length - 180), to: allTimes.length + 2 });
    return () => chart.remove();
  }, [data]);

  return <div ref={ref} style={{ height: 440, width: "100%" }} />;
}
