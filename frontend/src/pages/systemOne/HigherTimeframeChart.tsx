import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  LineSeries,
  LineStyle,
  type Time,
} from "lightweight-charts";
import type { SystemOneCandle } from "../../services/systemOneBacktestApi";
import { themeColors } from "./SystemOneChart";

/** Plain candles + RSI(14) pane with the 60 line, for the weekly / monthly
 *  charts the GFS setup reads. Data is exactly what the backend evaluated. */
export function HigherTimeframeChart({ candles }: { candles: SystemOneCandle[] }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || candles.length === 0) return;
    const c = themeColors();
    const chart = createChart(container, {
      layout: { background: { type: ColorType.Solid, color: c.bg }, textColor: c.text },
      grid: { vertLines: { color: c.grid }, horzLines: { color: c.grid } },
      timeScale: { borderColor: c.grid },
      rightPriceScale: { borderColor: c.grid },
      autoSize: true,
    });
    const series = chart.addSeries(CandlestickSeries, {
      upColor: c.up, downColor: c.down, borderUpColor: c.up, borderDownColor: c.down,
      wickUpColor: c.up, wickDownColor: c.down,
    });
    series.setData(
      candles.map((k) => ({ time: k.date.slice(0, 10) as Time, open: k.open, high: k.high, low: k.low, close: k.close })),
    );
    const rsi = chart.addSeries(
      LineSeries,
      { color: c.rsi, lineWidth: 2, title: "RSI 14", priceLineVisible: false },
      1,
    );
    rsi.setData(candles.filter((k) => k.rsi !== null).map((k) => ({ time: k.date.slice(0, 10) as Time, value: k.rsi as number })));
    rsi.createPriceLine({
      price: 60, color: c.ref, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: "60",
    });
    chart.panes()[0]?.setStretchFactor(3);
    chart.panes()[1]?.setStretchFactor(1);
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [candles]);

  if (candles.length === 0) {
    return <div className="state-subtitle">No completed bars to draw for this period.</div>;
  }
  return <div ref={containerRef} className="so-chart" />;
}
