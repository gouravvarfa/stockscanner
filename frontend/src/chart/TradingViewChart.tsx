import { useEffect, useRef, useState } from "react";
import { fetchCandles } from "./chartDatafeed";
import { IndicatorsMenu } from "./IndicatorsMenu";
import { OHLCReadout } from "./OHLCReadout";
import { TimeframeSelector } from "./TimeframeSelector";
import { DEFAULT_INDICATOR_SETTINGS, type ChartDataStatus, type ChartSignalContext, type IndicatorSettings, type OHLCBar, type Timeframe } from "./chartTypes";
import { useTradingViewChart, type ChartSeriesType } from "./useTradingViewChart";
import { useLiveChart } from "./useLiveChart";
import { INDICATOR_PREFS_STORAGE_KEY } from "./chartConfig";

// Live engine (backend/live/candle_builder.py) only builds these five
// timeframes — 1m/5m/30m/4H have no live candle to merge, so the chart
// simply never receives live updates for them (still shows historical
// data as before).
const LIVE_TIMEFRAME_KEY: Partial<Record<Timeframe, string>> = {
  "15m": "15m", "1H": "1H", "1D": "1D", "1W": "1W", "1M": "1M",
};

export interface TradingViewChartProps {
  symbol: string;
  signalContext: ChartSignalContext | null;
  isMaximized: boolean;
  onToggleMaximize: () => void;
  onClose: () => void;
}

function loadIndicatorPrefs(): IndicatorSettings {
  try {
    const raw = localStorage.getItem(INDICATOR_PREFS_STORAGE_KEY);
    if (!raw) return DEFAULT_INDICATOR_SETTINGS;
    return { ...DEFAULT_INDICATOR_SETTINGS, ...(JSON.parse(raw) as Partial<IndicatorSettings>) };
  } catch {
    return DEFAULT_INDICATOR_SETTINGS;
  }
}

function fmtRsi(value: number | null | undefined): string {
  return value === null || value === undefined || Number.isNaN(value) ? "—" : value.toFixed(1);
}

export function TradingViewChart({ symbol, signalContext, isMaximized, onToggleMaximize, onClose }: TradingViewChartProps) {
  const [timeframe, setTimeframe] = useState<Timeframe>("1D");
  const [chartType, setChartType] = useState<ChartSeriesType>("candles");
  const [indicators, setIndicators] = useState<IndicatorSettings>(loadIndicatorPrefs);
  const [status, setStatus] = useState<ChartDataStatus>("loading");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const requestIdRef = useRef(0);
  const barsRef = useRef<OHLCBar[]>([]);
  // Chart open -> live subscribe; chart close/unmount -> auto-unsubscribe
  // (see useLiveChart.ts's cleanup and backend/api/live.py's stream
  // lifetime) — the whole point of the 2026-09-25 "chart open flow" spec.
  const { liveCandles, status: liveStatus } = useLiveChart(symbol, true);

  useEffect(() => {
    try {
      localStorage.setItem(INDICATOR_PREFS_STORAGE_KEY, JSON.stringify(indicators));
    } catch {
      // best-effort only
    }
  }, [indicators]);

  const { crosshair, setData, fitContent, bollingerLatest, rsiLatest } = useTradingViewChart(containerRef, { indicators, chartType, timeframe });

  useEffect(() => {
    const controller = new AbortController();
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setStatus("loading");
    setErrorMessage(null);

    fetchCandles(symbol, timeframe, controller.signal, signalContext?.strategy === "CUP")
      .then((bars) => {
        if (requestIdRef.current !== requestId) return;
        if (bars.length === 0) {
          setStatus("empty");
          return;
        }
        barsRef.current = bars;
        setData(bars);
        setStatus("ready");
      })
      .catch((error: unknown) => {
        if (requestIdRef.current !== requestId || controller.signal.aborted) return;
        setStatus("error");
        setErrorMessage(error instanceof Error ? error.message : "Unable to load chart data.");
      });

    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, timeframe]);

  useEffect(() => {
    // LIVE candle merge (2026-09-25): updates only the CURRENT candle in
    // place — historical (completed) bars from fetchCandles() are never
    // touched, so this can never retroactively change a confirmed bar.
    const liveKey = LIVE_TIMEFRAME_KEY[timeframe];
    if (!liveKey || !liveCandles || barsRef.current.length === 0) return;
    const live = liveCandles[liveKey];
    if (!live) return;

    const bars = barsRef.current;
    const last = bars[bars.length - 1];
    const liveBar: OHLCBar = { time: live.time, open: live.open, high: live.high, low: live.low, close: live.close, volume: live.volume };
    const merged = last && last.time === live.time ? [...bars.slice(0, -1), liveBar] : [...bars, liveBar];
    barsRef.current = merged;
    setData(merged);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [liveCandles, timeframe]);

  return (
    <div className={isMaximized ? "chart-panel chart-panel-maximized" : "chart-panel"}>
      <div className="chart-panel-header">
        <div className="chart-panel-title">
          <strong>{symbol}</strong>
          {signalContext && <span className="chip chip-pass">{signalContext.strategy}</span>}
          {LIVE_TIMEFRAME_KEY[timeframe] && (
            <span className={liveStatus === "CONNECTED" ? "chip chip-pass" : "chip"} title="Live Angel One connection status">
              {liveStatus === "CONNECTED" ? "● LIVE" : liveStatus === "RECONNECTING" ? "RECONNECTING…" : "LAST CLOSE"}
            </span>
          )}
        </div>
        <div className="chart-panel-actions">
          <button type="button" className="icon-button" aria-label={isMaximized ? "Restore" : "Maximize"} onClick={onToggleMaximize}>
            {isMaximized ? "⤡" : "⤢"}
          </button>
          <button type="button" className="icon-button" aria-label="Close chart" onClick={onClose}>
            ✕
          </button>
        </div>
      </div>

      {signalContext && (
        <div className="chart-signal-context">
          <span>Daily RSI <strong>{fmtRsi(signalContext.daily_rsi)}</strong></span>
          <span>Weekly RSI <strong>{fmtRsi(signalContext.weekly_rsi)}</strong></span>
          <span>Monthly RSI <strong>{fmtRsi(signalContext.monthly_rsi)}</strong></span>
          {signalContext.divergence_timeframe && <span>Signal TF <strong>{signalContext.divergence_timeframe}</strong></span>}
          {signalContext.signal_date && <span>Signal Date <strong>{new Date(signalContext.signal_date).toLocaleDateString()}</strong></span>}
        </div>
      )}

      <div className="chart-panel-body">
        <div className="chart-toolbar">
          <TimeframeSelector value={timeframe} onChange={setTimeframe} />
          <div className="chart-toolbar-right">
            <div className="chart-type-toggle">
              <button
                type="button"
                className={chartType === "candles" ? "chart-toolbar-btn active" : "chart-toolbar-btn"}
                onClick={() => setChartType("candles")}
              >
                Candles
              </button>
              <button
                type="button"
                className={chartType === "line" ? "chart-toolbar-btn active" : "chart-toolbar-btn"}
                onClick={() => setChartType("line")}
              >
                Line
              </button>
            </div>
            <IndicatorsMenu value={indicators} onChange={setIndicators} />
            <button type="button" className="chart-toolbar-btn" aria-label="Reset zoom" onClick={fitContent}>
              Reset Zoom
            </button>
          </div>
        </div>

        <div className="chart-canvas-wrap">
          <div className="chart-legend-overlay">
            {indicators.bollinger && bollingerLatest && (
              <span className="chart-indicator-legend">
                BB ({indicators.bollingerPeriod}, {indicators.bollingerMultiplier}){" "}
                <span className="bb-upper-lower">{bollingerLatest.upper.toFixed(2)}</span>{" "}
                <span className="bb-mid">{bollingerLatest.middle.toFixed(2)}</span>{" "}
                <span className="bb-upper-lower">{bollingerLatest.lower.toFixed(2)}</span>
              </span>
            )}
            {indicators.rsi && rsiLatest !== null && (
              <span className="chart-indicator-legend">
                RSI ({indicators.rsiPeriod}) <strong>{rsiLatest.toFixed(2)}</strong>
              </span>
            )}
            <OHLCReadout readout={crosshair} />
          </div>
          <div ref={containerRef} className="chart-canvas-el" />

          {status !== "ready" && (
            <div className="chart-status-overlay">
              {status === "loading" && <p>Loading {symbol} — {timeframe}…</p>}
              {status === "empty" && <p>No historical data available for {symbol} on {timeframe}.</p>}
              {status === "error" && (
                <>
                  <p><strong>{errorMessage ?? "Unable to load chart data."}</strong></p>
                  <p className="chart-status-sub">Angel One may be rate-limited, disconnected, or this symbol/timeframe is unsupported.</p>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

