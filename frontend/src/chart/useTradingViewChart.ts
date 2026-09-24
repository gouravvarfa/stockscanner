import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  createChart,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type LineData,
  type Time,
} from "lightweight-charts";
import {
  MIN_RSI_PANE_HEIGHT,
  MIN_VOLUME_PANE_HEIGHT,
  RSI_PANE_INDEX,
  RSI_PANE_RATIO,
  VOLUME_PANE_INDEX,
  VOLUME_PANE_RATIO,
} from "./chartConfig";
import { calculateBollingerBands, calculateRSI } from "./chartStudies";
import { getChartThemeColors } from "./chartTheme";
import type { IndicatorSettings, OHLCBar } from "./chartTypes";

export interface CrosshairReadout {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface BollingerLatest {
  upper: number;
  middle: number;
  lower: number;
}

export type ChartSeriesType = "candles" | "line";

interface UseTradingViewChartOptions {
  indicators: IndicatorSettings;
  chartType?: ChartSeriesType;
}

/**
 * Owns the lightweight-charts instance for its lifetime: creates it once,
 * wires up the candlestick series, and adds/removes the volume/Bollinger/
 * RSI panes as indicator settings change. Pure chart mechanics — knows
 * nothing about scanner data or the Angel One datafeed. Modeled on the
 * Trading Journal app's useTradingChart.ts (chart-mechanics hook kept
 * separate from data-fetching), minus its trade-marker/drawing-tool
 * features which don't apply here.
 */
export function useTradingViewChart(containerRef: React.RefObject<HTMLDivElement | null>, options: UseTradingViewChartOptions) {
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const closeLineSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const bbUpperRef = useRef<ISeriesApi<"Line"> | null>(null);
  const bbMiddleRef = useRef<ISeriesApi<"Line"> | null>(null);
  const bbLowerRef = useRef<ISeriesApi<"Line"> | null>(null);
  const rsiSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const rsiPriceLinesRef = useRef<IPriceLine[]>([]);
  const barsRef = useRef<OHLCBar[]>([]);
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const [crosshair, setCrosshair] = useState<CrosshairReadout | null>(null);
  const [bollingerLatest, setBollingerLatest] = useState<BollingerLatest | null>(null);
  const [rsiLatest, setRsiLatest] = useState<number | null>(null);

  const syncPaneHeights = (): void => {
    const chart = chartRef.current;
    const container = containerRef.current;
    if (!chart || !container) return;
    const total = container.clientHeight;
    const volumeHeight = volumeSeriesRef.current ? Math.max(MIN_VOLUME_PANE_HEIGHT, Math.round(total * VOLUME_PANE_RATIO)) : 0;
    const rsiHeight = rsiSeriesRef.current ? Math.max(MIN_RSI_PANE_HEIGHT, Math.round(total * RSI_PANE_RATIO)) : 0;
    const priceHeight = Math.max(240, total - volumeHeight - rsiHeight);
    chart.panes()[0]?.setHeight(priceHeight);
    if (volumeSeriesRef.current) chart.panes()[VOLUME_PANE_INDEX]?.setHeight(volumeHeight);
    if (rsiSeriesRef.current) chart.panes()[RSI_PANE_INDEX]?.setHeight(rsiHeight);
  };

  const recalcIndicators = (): void => {
    const bars = barsRef.current;
    const closes = bars.map((bar) => bar.close);

    if (bbUpperRef.current && bbMiddleRef.current && bbLowerRef.current) {
      const { upper, middle, lower } = calculateBollingerBands(
        closes,
        optionsRef.current.indicators.bollingerPeriod,
        optionsRef.current.indicators.bollingerMultiplier,
      );
      bbUpperRef.current.setData(toLineData(bars, upper));
      bbMiddleRef.current.setData(toLineData(bars, middle));
      bbLowerRef.current.setData(toLineData(bars, lower));
      const lastIndex = closes.length - 1;
      if (lastIndex >= 0 && upper[lastIndex] !== null) {
        setBollingerLatest({ upper: upper[lastIndex] as number, middle: middle[lastIndex] as number, lower: lower[lastIndex] as number });
      } else {
        setBollingerLatest(null);
      }
    } else {
      setBollingerLatest(null);
    }

    if (rsiSeriesRef.current) {
      const rsi = calculateRSI(closes, optionsRef.current.indicators.rsiPeriod);
      rsiSeriesRef.current.setData(toLineData(bars, rsi));
      const lastIndex = rsi.length - 1;
      setRsiLatest(lastIndex >= 0 ? rsi[lastIndex] : null);
    } else {
      setRsiLatest(null);
    }
  };

  // Chart creation — runs once for the component's lifetime.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const colors = getChartThemeColors();
    const chart = createChart(container, {
      layout: { background: { color: colors.background }, textColor: colors.text, fontFamily: "inherit" },
      grid: { vertLines: { color: colors.grid }, horzLines: { color: colors.grid } },
      rightPriceScale: { borderColor: colors.border },
      timeScale: { borderColor: colors.border, timeVisible: true },
      crosshair: { mode: 0 },
      autoSize: false,
      width: container.clientWidth,
      height: container.clientHeight,
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: colors.success,
      downColor: colors.danger,
      borderUpColor: colors.success,
      borderDownColor: colors.danger,
      wickUpColor: colors.success,
      wickDownColor: colors.danger,
    });
    candleSeriesRef.current = candleSeries;

    // A plain close-price line — the alternative to candles, toggled via
    // the header's Candles/Line switch (chartType option below). Created
    // up front (hidden by default) so switching types never re-fetches or
    // re-renders the underlying data, only which series is visible.
    const closeLineSeries = chart.addSeries(LineSeries, { color: colors.purple, lineWidth: 2, visible: false });
    closeLineSeriesRef.current = closeLineSeries;

    chart.subscribeCrosshairMove((param) => {
      if (!param.time || !param.seriesData) {
        setCrosshair(null);
        return;
      }
      const data = param.seriesData.get(candleSeries) as { open: number; high: number; low: number; close: number } | undefined;
      if (data) {
        setCrosshair({ time: toSeconds(param.time), open: data.open, high: data.high, low: data.low, close: data.close });
        return;
      }
      // Candle series is hidden in line-chart mode — only its close value is available.
      const lineData = param.seriesData.get(closeLineSeries) as { value: number } | undefined;
      if (!lineData) {
        setCrosshair(null);
        return;
      }
      setCrosshair({ time: toSeconds(param.time), open: lineData.value, high: lineData.value, low: lineData.value, close: lineData.value });
    });

    let lastWidth = container.clientWidth;
    const resizeObserver = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) {
        chart.resize(width, height);
        syncPaneHeights();
        if (Math.abs(width - lastWidth) > 80) {
          chart.timeScale().fitContent();
        }
        lastWidth = width;
      }
    });
    resizeObserver.observe(container);

    chartRef.current = chart;

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      closeLineSeriesRef.current = null;
      volumeSeriesRef.current = null;
      bbUpperRef.current = null;
      bbMiddleRef.current = null;
      bbLowerRef.current = null;
      rsiSeriesRef.current = null;
      rsiPriceLinesRef.current = [];
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Re-theme the existing chart instance when the app's light/dark theme
  // changes while the drawer stays open (chart is not recreated).
  useEffect(() => {
    const observer = new MutationObserver(() => {
      const chart = chartRef.current;
      if (!chart) return;
      const colors = getChartThemeColors();
      chart.applyOptions({
        layout: { background: { color: colors.background }, textColor: colors.text },
        grid: { vertLines: { color: colors.grid }, horzLines: { color: colors.grid } },
        rightPriceScale: { borderColor: colors.border },
        timeScale: { borderColor: colors.border },
      });
      candleSeriesRef.current?.applyOptions({
        upColor: colors.success, downColor: colors.danger,
        borderUpColor: colors.success, borderDownColor: colors.danger,
        wickUpColor: colors.success, wickDownColor: colors.danger,
      });
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);

  // Volume pane.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !options.indicators.volume) {
      syncPaneHeights();
      return;
    }
    const colors = getChartThemeColors();
    const volumeSeries = chart.addSeries(HistogramSeries, { priceFormat: { type: "volume" }, color: colors.muted }, VOLUME_PANE_INDEX);
    volumeSeriesRef.current = volumeSeries;
    if (barsRef.current.length > 0) {
      volumeSeries.setData(barsRef.current.map((bar) => toVolumePoint(bar, colors)));
    }
    syncPaneHeights();
    return () => {
      try {
        chart.removeSeries(volumeSeries);
      } catch {
        // chart already disposed
      }
      volumeSeriesRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [options.indicators.volume]);

  // Bollinger Bands overlay.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !options.indicators.bollinger) {
      setBollingerLatest(null);
      return;
    }
    const colors = getChartThemeColors();
    const upper = chart.addSeries(LineSeries, { color: colors.purple, lineWidth: 1, title: "BB Upper" });
    const middle = chart.addSeries(LineSeries, { color: colors.warning, lineWidth: 1, title: "BB Mid" });
    const lower = chart.addSeries(LineSeries, { color: colors.purple, lineWidth: 1, title: "BB Lower" });
    bbUpperRef.current = upper;
    bbMiddleRef.current = middle;
    bbLowerRef.current = lower;
    recalcIndicators();
    return () => {
      try {
        chart.removeSeries(upper);
        chart.removeSeries(middle);
        chart.removeSeries(lower);
      } catch {
        // chart already disposed
      }
      bbUpperRef.current = null;
      bbMiddleRef.current = null;
      bbLowerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [options.indicators.bollinger, options.indicators.bollingerPeriod, options.indicators.bollingerMultiplier]);

  // RSI pane — with configurable overbought/oversold reference lines.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !options.indicators.rsi) {
      setRsiLatest(null);
      syncPaneHeights();
      return;
    }
    const colors = getChartThemeColors();
    const rsiSeries = chart.addSeries(LineSeries, { color: colors.purple, lineWidth: 2 }, RSI_PANE_INDEX);
    rsiSeriesRef.current = rsiSeries;
    rsiPriceLinesRef.current = [
      rsiSeries.createPriceLine({
        price: options.indicators.rsiUpper, color: colors.danger, lineWidth: 2, lineStyle: 2,
        axisLabelVisible: true, title: `${options.indicators.rsiUpper} Overbought`,
      }),
      rsiSeries.createPriceLine({
        price: options.indicators.rsiLower, color: colors.success, lineWidth: 2, lineStyle: 2,
        axisLabelVisible: true, title: `${options.indicators.rsiLower} Oversold`,
      }),
    ];
    recalcIndicators();
    syncPaneHeights();
    return () => {
      try {
        chart.removeSeries(rsiSeries);
      } catch {
        // chart already disposed
      }
      rsiSeriesRef.current = null;
      rsiPriceLinesRef.current = [];
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [options.indicators.rsi, options.indicators.rsiPeriod, options.indicators.rsiUpper, options.indicators.rsiLower]);

  // Candles/Line toggle — both series always hold the same data; only
  // which one is visible changes, so switching is instant (no re-fetch).
  useEffect(() => {
    const isLine = options.chartType === "line";
    candleSeriesRef.current?.applyOptions({ visible: !isLine });
    closeLineSeriesRef.current?.applyOptions({ visible: isLine });
  }, [options.chartType]);

  const setData = (bars: OHLCBar[]): void => {
    barsRef.current = bars;
    candleSeriesRef.current?.setData(bars.map((bar) => ({ time: bar.time as Time, open: bar.open, high: bar.high, low: bar.low, close: bar.close })));
    closeLineSeriesRef.current?.setData(bars.map((bar) => ({ time: bar.time as Time, value: bar.close })));
    if (volumeSeriesRef.current) {
      const colors = getChartThemeColors();
      volumeSeriesRef.current.setData(bars.map((bar) => toVolumePoint(bar, colors)));
    }
    chartRef.current?.timeScale().fitContent();
    recalcIndicators();
  };

  const fitContent = (): void => {
    chartRef.current?.timeScale().fitContent();
  };

  return { crosshair, setData, fitContent, bollingerLatest, rsiLatest };
}

function toSeconds(time: Time): number {
  return typeof time === "number" ? time : Math.floor(Date.parse(String(time)) / 1000);
}

function toVolumePoint(bar: OHLCBar, colors: { success: string; danger: string }) {
  return {
    time: bar.time as Time,
    value: bar.volume ?? 0,
    color: bar.close >= bar.open ? colors.success : colors.danger,
  };
}

function toLineData(bars: OHLCBar[], values: Array<number | null>): LineData<Time>[] {
  const points: LineData<Time>[] = [];
  bars.forEach((bar, index) => {
    const value = values[index];
    if (value !== null && value !== undefined) {
      points.push({ time: bar.time as Time, value });
    }
  });
  return points;
}
