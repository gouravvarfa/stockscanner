import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  LineSeries,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import type { SystemOneBacktest } from "../../services/systemOneBacktestApi";
import { isIntraday, timeframeNoun } from "./timeframes";

// Daily/weekly candles carry only a date, so they use plain "YYYY-MM-DD" times
// (no timezone shifting). Hourly candles need a time of day: the backend sends
// naive exchange-time stamps, which are read as-is (as UTC) so the axis shows
// the same clock times as the table.
function toTime(iso: string, intraday: boolean): Time {
  return intraday
    ? (Math.floor(Date.parse(`${iso.slice(0, 19)}Z`) / 1000) as UTCTimestamp)
    : (iso.slice(0, 10) as Time);
}

function shiftDays(iso: string, days: number, intraday: boolean): Time {
  if (intraday) return ((toTime(iso, true) as number) + days * 86400) as UTCTimestamp;
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10) as Time;
}

function compareTime(a: Time, b: Time): number {
  return typeof a === "number" && typeof b === "number" ? a - b : String(a).localeCompare(String(b));
}

function themeColors() {
  const root = document.documentElement;
  const isDark =
    root.getAttribute("data-theme") === "dark" ||
    (!root.hasAttribute("data-theme") && window.matchMedia("(prefers-color-scheme: dark)").matches);
  return isDark
    ? { bg: "#0f1115", text: "#c9ced6", grid: "#1d2129", up: "#26a69a", down: "#ef5350", ma: "#f59e0b", rsi: "#a78bfa", ref: "#64748b" }
    : { bg: "#ffffff", text: "#1a1d23", grid: "#eef0f3", up: "#16a34a", down: "#dc2626", ma: "#d97706", rsi: "#7c3aed", ref: "#94a3b8" };
}

interface Props {
  result: SystemOneBacktest;
  focusedTradeNumber: number | null;
}

/** Weekly candles + 20 MA, entry/exit markers, and an RSI(14) pane with the
 *  60 trigger line. Every series comes straight from the backtest response,
 *  so what is drawn is exactly what the strategy evaluated. */
export function SystemOneChart({ result, focusedTradeNumber }: Props) {
  const intraday = isIntraday(result.timeframe);
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const maRef = useRef<ISeriesApi<"Line"> | null>(null);
  const rsiRef = useRef<ISeriesApi<"Line"> | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const c = themeColors();

    const chart = createChart(container, {
      layout: { background: { type: ColorType.Solid, color: c.bg }, textColor: c.text },
      grid: { vertLines: { color: c.grid }, horzLines: { color: c.grid } },
      timeScale: { borderColor: c.grid },
      rightPriceScale: { borderColor: c.grid },
      autoSize: true,
    });

    const candles = chart.addSeries(CandlestickSeries, {
      upColor: c.up, downColor: c.down, borderUpColor: c.up, borderDownColor: c.down,
      wickUpColor: c.up, wickDownColor: c.down,
    });
    const ma = chart.addSeries(LineSeries, {
      color: c.ma, lineWidth: 2, title: "20 MA", priceLineVisible: false, lastValueVisible: false,
    });
    // Markers plugin is created once and updated with setMarkers() — creating
    // a new one on every data change would stack plugins on the same series.
    markersRef.current = createSeriesMarkers(candles, []);

    const rsi = chart.addSeries(
      LineSeries,
      { color: c.rsi, lineWidth: 2, title: "RSI 14", priceLineVisible: false },
      1,
    );
    rsi.createPriceLine({
      price: 60, color: c.ref, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: "60",
    });

    // Stretch factors rather than setHeight(): each setHeight takes space from a
    // neighbouring pane, so the final split would depend on call order.
    chart.panes()[0]?.setStretchFactor(3);
    chart.panes()[1]?.setStretchFactor(1);

    chartRef.current = chart;
    candleRef.current = candles;
    maRef.current = ma;
    rsiRef.current = rsi;

    return () => {
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
      maRef.current = null;
      rsiRef.current = null;
      markersRef.current = null;
    };
  }, []);

  // Data effect: depends only on `result`, so focusing a trade never reloads data.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !candleRef.current || !maRef.current || !rsiRef.current) return;

    chart.applyOptions({ timeScale: { timeVisible: intraday, secondsVisible: false } });
    candleRef.current.setData(
      result.candles.map((k) => ({ time: toTime(k.date, intraday), open: k.open, high: k.high, low: k.low, close: k.close })),
    );
    maRef.current.setData(
      result.candles.filter((k) => k.ma !== null).map((k) => ({ time: toTime(k.date, intraday), value: k.ma as number })),
    );
    rsiRef.current.setData(
      result.candles.filter((k) => k.rsi !== null).map((k) => ({ time: toTime(k.date, intraday), value: k.rsi as number })),
    );

    const c = themeColors();
    const markers: SeriesMarker<Time>[] = [];
    for (const t of result.trades) {
      markers.push({
        time: toTime(t.entry_date, intraday), position: "belowBar", color: c.up, shape: "arrowUp", text: `Entry ${t.entry_price.toFixed(2)}`,
      });
      if (t.exit_date && t.exit_price !== null) {
        const won = (t.pnl_amount ?? 0) >= 0;
        markers.push({
          time: toTime(t.exit_date, intraday), position: "aboveBar", color: won ? c.up : c.down, shape: "arrowDown",
          text: `Exit ${t.exit_price.toFixed(2)}`,
        });
      }
    }
    // Markers must be ascending by time; an exit and the next entry can share a candle.
    markers.sort((a, b) => compareTime(a.time, b.time));
    markersRef.current?.setMarkers(markers);

    chart.timeScale().fitContent();
  }, [result, intraday]);

  // Focus effect: only moves the visible range; the full history stays loaded.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    if (focusedTradeNumber === null) {
      chart.timeScale().fitContent();
      return;
    }
    const trade = result.trades.find((t) => t.trade_number === focusedTradeNumber);
    if (!trade) return;
    const end = trade.exit_date ?? result.candles[result.candles.length - 1]?.date ?? trade.entry_date;
    try {
      // About 10 weeks of context on a daily/weekly chart, 5 days on an intraday one.
      const pad = intraday ? 5 : 70;
      chart.timeScale().setVisibleRange({
        from: shiftDays(trade.entry_date, -pad, intraday),
        to: shiftDays(end, pad, intraday),
      });
    } catch {
      // A range the library cannot satisfy must not take the page down.
    }
  }, [focusedTradeNumber, result, intraday]);

  if (result.candles.length === 0) {
    return <div className="state-subtitle">No candles to draw for this period.</div>;
  }

  return (
    <div>
      <p className="so-chart-legend">
        <span style={{ color: "#f59e0b", fontWeight: 600 }}>Orange</span> = 20 MA (its value at entry is the stop loss; exit when a {timeframeNoun(result.timeframe)}
        candle touches that stop) · <span style={{ color: "#7c3aed", fontWeight: 600 }}>Purple</span> = RSI(14), buy trigger
        when it crosses above the dashed 60 line.{" "}
        {focusedTradeNumber === null
          ? "Click a trade row to zoom to it."
          : `Zoomed to trade #${focusedTradeNumber}. Click the row again to zoom out.`}
      </p>
      <div ref={containerRef} className="so-chart" />
    </div>
  );
}
