import { useEffect, useRef } from "react";
import {
  ColorType,
  createChart,
  createSeriesMarkers,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import type { BacktestResult } from "../../services/topBottomApi";

// Deliberately a NEW, standalone lightweight-charts instance — not a reuse
// of frontend/src/chart/useTradingViewChart.ts (the existing scanner Chart
// feature). Top-Bottom needs a LINE-ONLY view with its own marker set; the
// existing candlestick+RSI+BB chart component is left completely untouched.

function toTime(iso: string): UTCTimestamp {
  return Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp;
}

/** Collapse duplicate timestamps, keeping the LAST value — lightweight-charts
 *  requires a strictly ascending, unique time axis. */
function dedupeAscending(points: { time: UTCTimestamp; value: number }[]) {
  const byTime = new Map<number, number>();
  for (const p of points) byTime.set(p.time, p.value);
  return Array.from(byTime.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([time, value]) => ({ time: time as Time, value }));
}

interface Props {
  result: BacktestResult;
  focusedTradeNumber: number | null;
}

export function TopBottomChart({ result, focusedTradeNumber }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const priceRef = useRef<ISeriesApi<"Line"> | null>(null);
  const systemRef = useRef<ISeriesApi<"Line"> | null>(null);
  const stopRef = useRef<ISeriesApi<"Line"> | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const isDark = document.documentElement.getAttribute("data-theme") === "dark"
      || (!document.documentElement.hasAttribute("data-theme") && window.matchMedia("(prefers-color-scheme: dark)").matches);
    const colors = isDark
      ? { bg: "#0f1115", text: "#c9ced6", grid: "#1d2129", line: "#4da3ff" }
      : { bg: "#ffffff", text: "#1a1d23", grid: "#eef0f3", line: "#2563eb" };

    const chart = createChart(container, {
      layout: { background: { type: ColorType.Solid, color: colors.bg }, textColor: colors.text },
      grid: { vertLines: { color: colors.grid }, horzLines: { color: colors.grid } },
      timeScale: { timeVisible: true, borderColor: colors.grid },
      rightPriceScale: { borderColor: colors.grid },
      autoSize: true,
    });

    priceRef.current = chart.addSeries(LineSeries, { color: colors.line, lineWidth: 2, title: "Close" });
    // GREEN = active System Point / entry trigger. RED = active (trailing)
    // Stop Loss. Stepped, because a level holds until structure moves it —
    // and a line moving is NOT a trade, only a close crossing one is.
    systemRef.current = chart.addSeries(LineSeries, {
      color: "#22c55e", lineWidth: 2, lineStyle: 0, title: "System Point",
      lastValueVisible: false, priceLineVisible: false,
    });
    stopRef.current = chart.addSeries(LineSeries, {
      color: "#ef4444", lineWidth: 2, lineStyle: 0, title: "Stop Loss",
      lastValueVisible: false, priceLineVisible: false,
    });

    // The markers plugin is created ONCE and updated via setMarkers().
    // Calling createSeriesMarkers on every data change attaches a new
    // plugin instance to the same series each time, which both leaks and
    // can throw once several are stacked up.
    markersRef.current = createSeriesMarkers(priceRef.current, []);

    chartRef.current = chart;

    return () => {
      chart.remove();
      chartRef.current = null;
      priceRef.current = null;
      systemRef.current = null;
      stopRef.current = null;
      markersRef.current = null;
    };
  }, []);

  // Data effect — depends ONLY on `result`, never on the focused trade, so
  // selecting a trade can never remove historical data from the chart.
  useEffect(() => {
    const chart = chartRef.current;
    const price = priceRef.current;
    const system = systemRef.current;
    const stop = stopRef.current;
    if (!chart || !price || !system || !stop) return;

    price.setData(dedupeAscending(result.price_series.map((p) => ({ time: toTime(p.date), value: p.close }))));
    system.setData(dedupeAscending(result.system_point_line.map((p) => ({ time: toTime(p.date), value: p.value }))));
    stop.setData(dedupeAscending(result.stop_loss_line.map((p) => ({ time: toTime(p.date), value: p.value }))));

    // Markers: ONLY real trade events (entry/exit) — never an arrow per
    // detected Top/Bottom, which are structure, not signals.
    const markers: SeriesMarker<Time>[] = [];
    for (const t of result.trades) {
      markers.push({
        time: toTime(t.entry_date) as Time,
        position: t.direction === "BUY" ? "belowBar" : "aboveBar",
        color: t.direction === "BUY" ? "#22c55e" : "#ef4444",
        shape: t.direction === "BUY" ? "arrowUp" : "arrowDown",
        text: `${t.direction} ENTRY`,
        size: 1,
      });
      if (t.exit_date && t.exit_price !== null) {
        markers.push({
          time: toTime(t.exit_date) as Time,
          position: t.direction === "BUY" ? "aboveBar" : "belowBar",
          color: "#94a3b8",
          shape: "circle",
          text: `${t.direction} EXIT`,
          size: 0.9,
        });
      }
    }
    // Must be ascending by time — on a reversal the outgoing trade's EXIT
    // and the incoming trade's ENTRY land on the very same bar.
    markers.sort((a, b) => (a.time as number) - (b.time as number));
    markersRef.current?.setMarkers(markers);

    chart.timeScale().fitContent();
  }, [result]);

  // Focus effect — ZOOMS to the selected trade by moving the visible range.
  // It never calls setData, so the full history stays loaded and the user
  // can pan/zoom back out to it.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    if (focusedTradeNumber === null) {
      chart.timeScale().fitContent();
      return;
    }

    const trade = result.trades.find((t) => t.trade_number === focusedTradeNumber);
    if (!trade) return;

    const from = toTime(trade.entry_date);
    const to = trade.exit_date ? toTime(trade.exit_date) : from;
    const pad = Math.max(Math.round((to - from) * 0.4), 3 * 24 * 60 * 60);
    try {
      chart.timeScale().setVisibleRange({
        from: (from - pad) as Time,
        to: (to + pad) as Time,
      });
    } catch {
      // A range the library can't satisfy (e.g. entirely outside the
      // loaded data) must not take the page down — the chart simply
      // stays where it is.
    }
  }, [focusedTradeNumber, result]);

  return (
    <div>
      <p style={{ fontSize: 12, opacity: 0.7, marginTop: 0 }}>
        <span style={{ color: "#22c55e", fontWeight: 600 }}>Green</span> = active System Point (entry trigger) ·{" "}
        <span style={{ color: "#ef4444", fontWeight: 600 }}>Red</span> = active trailing Stop Loss.{" "}
        {focusedTradeNumber === null
          ? "Click a row in Trade Results to zoom to that trade (full history stays loaded)."
          : `Zoomed to trade #${focusedTradeNumber}. Click the row again to zoom back out.`}
      </p>
      <div ref={containerRef} style={{ width: "100%", height: 460 }} />
    </div>
  );
}
