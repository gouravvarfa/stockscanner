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
import type { ChartTimeSync } from "./chartTimeSync";
import { attachOhlcLegend, type OhlcBar } from "./ohlcLegend";

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

export function themeColors() {
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
  /** GFS: the buy trigger is the GFS setup (not an RSI cross of 60), so the legend says so. */
  gfsSetup?: boolean;
  /** GFS: keeps this chart's date window equal to the weekly/monthly charts. */
  sync?: ChartTimeSync;
}

/** Weekly candles + 20 MA, entry/exit markers, and an RSI(14) pane with the
 *  60 trigger line. Every series comes straight from the backtest response,
 *  so what is drawn is exactly what the strategy evaluated. */
export function SystemOneChart({ result, focusedTradeNumber, gfsSetup = false, sync }: Props) {
  const intraday = isIntraday(result.timeframe);
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const maRef = useRef<ISeriesApi<"Line"> | null>(null);
  const rsiRef = useRef<ISeriesApi<"Line"> | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const legendBarsRef = useRef<OhlcBar[]>([]);
  const legendRefreshRef = useRef<(() => void) | null>(null);

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
      {
        color: c.rsi, lineWidth: 2, title: "RSI 14", priceLineVisible: false,
        // Keep 40 and 60 (with some room around them) inside the RSI pane even when RSI stays in a narrow
        // band, so both reference lines are always on screen.
        autoscaleInfoProvider: (original: () => { priceRange: { minValue: number; maxValue: number } | null; margins?: { above: number; below: number } } | null) => {
          const base = original();
          const lo = Math.min(base?.priceRange?.minValue ?? 30, 30);
          const hi = Math.max(base?.priceRange?.maxValue ?? 70, 70);
          return { priceRange: { minValue: lo, maxValue: hi }, margins: base?.margins };
        },
      },
      1,
    );
    // Solid lines across the whole RSI pane: 60 = buy trigger (green), 40 = lower line (red).
    rsi.createPriceLine({
      price: 60, color: c.up, lineWidth: 2, lineStyle: LineStyle.Solid, axisLabelVisible: true, title: "60",
    });
    rsi.createPriceLine({
      price: 40, color: c.down, lineWidth: 2, lineStyle: LineStyle.Solid, axisLabelVisible: true, title: "40",
    });

    // Stretch factors rather than setHeight(): each setHeight takes space from a
    // neighbouring pane, so the final split would depend on call order.
    chart.panes()[0]?.setStretchFactor(3);
    chart.panes()[1]?.setStretchFactor(1);

    chartRef.current = chart;
    candleRef.current = candles;
    maRef.current = ma;
    rsiRef.current = rsi;
    const unsync = sync?.add(chart, container);
    // The legend reads the bars from a ref so it always shows the current result.
    const detachLegend = attachOhlcLegend(container, chart, candles, legendBarsRef.current, c);

    legendRefreshRef.current = detachLegend.refresh;

    return () => {
      legendRefreshRef.current = null;
      detachLegend();
      unsync?.();
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
      maRef.current = null;
      rsiRef.current = null;
      markersRef.current = null;
    };
  }, [sync]);

  // Data effect: depends only on `result`, so focusing a trade never reloads data.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !candleRef.current || !maRef.current || !rsiRef.current) return;

    chart.applyOptions({ timeScale: { timeVisible: intraday, secondsVisible: false } });
    const bars = result.candles.map((k) => ({ time: toTime(k.date, intraday), open: k.open, high: k.high, low: k.low, close: k.close }));
    legendBarsRef.current.splice(0, legendBarsRef.current.length, ...bars);
    candleRef.current.setData(bars);
    legendRefreshRef.current?.();
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
    // Programmatic moves go through the sync group so weekly/monthly follow.
    const move = (fn: () => void) => (sync ? sync.drive(chart, fn) : fn());
    if (focusedTradeNumber === null) {
      move(() => chart.timeScale().fitContent());
      return;
    }
    const trade = result.trades.find((t) => t.trade_number === focusedTradeNumber);
    if (!trade) return;
    const end = trade.exit_date ?? result.candles[result.candles.length - 1]?.date ?? trade.entry_date;
    try {
      // About 10 weeks of context on a daily/weekly chart, 5 days on an intraday one.
      const pad = intraday ? 5 : 70;
      move(() =>
        chart.timeScale().setVisibleRange({
          from: shiftDays(trade.entry_date, -pad, intraday),
          to: shiftDays(end, pad, intraday),
        }),
      );
    } catch {
      // A range the library cannot satisfy must not take the page down.
    }
  }, [focusedTradeNumber, result, intraday, sync]);

  if (result.candles.length === 0) {
    return <div className="state-subtitle">No candles to draw for this period.</div>;
  }

  return (
    <div>
      <p className="so-chart-legend">
        {gfsSetup ? (
          <>
            <span style={{ color: "#7c3aed", fontWeight: 600 }}>Purple</span> = daily RSI(14). Entry is the next candle&apos;s
            close after the signal. The stop starts at the lowest low of the last 5 candles, moves to the entry after a
            close 1R above it, then trails up while the last 3 candles make higher lows. Exit at the open on a gap below
            the stop, at the stop when the low touches it, or at the close when the weekly RSI is below 60.
          </>
        ) : (
          <>
            <span style={{ color: "#f59e0b", fontWeight: 600 }}>Orange</span> = 20 MA (the stop for each {timeframeNoun(result.timeframe)} candle is the previous candle&apos;s
            value; exit at the open on a gap below it, otherwise at the stop when the low touches it) · <span style={{ color: "#7c3aed", fontWeight: 600 }}>Purple</span> = RSI(14), buy trigger
            when it crosses above the green 60 line (red line = 40).
          </>
        )}{" "}
        {focusedTradeNumber === null
          ? "Click a trade row to zoom to it."
          : `Zoomed to trade #${focusedTradeNumber}. Click the row again to zoom out.`}
      </p>
      <div ref={containerRef} className="so-chart" />
    </div>
  );
}
