import { useEffect, useRef, useState } from "react";
import { fetchCandles } from "./chartDatafeed";
import { IndicatorsMenu } from "./IndicatorsMenu";
import { OHLCReadout, fmtVolume } from "./OHLCReadout";
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

const INTRADAY = new Set<Timeframe>(["1m", "5m", "15m", "30m", "1H", "4H"]);

/** Hovered bar's date (and time, on intraday) for the legend. Bar times are UTC-labelled wall-clock. */
function fmtLegendTime(seconds: number, timeframe: Timeframe): string {
  const d = new Date(seconds * 1000);
  const opts: Intl.DateTimeFormatOptions = timeframe === "1M"
    ? { month: "short", year: "numeric", timeZone: "UTC" }
    : { day: "2-digit", month: "short", year: "2-digit", timeZone: "UTC" };
  if (INTRADAY.has(timeframe)) Object.assign(opts, { hour: "2-digit", minute: "2-digit", hour12: false });
  return d.toLocaleString("en-IN", opts);
}

/** Only the signal-context values that actually exist — no rows of "—". */
function signalContextItems(ctx: ChartSignalContext | null): Array<[string, string]> {
  if (!ctx) return [];
  const items: Array<[string, string]> = [];
  if (ctx.daily_rsi != null) items.push(["Daily RSI", fmtRsi(ctx.daily_rsi)]);
  if (ctx.weekly_rsi != null) items.push(["Weekly RSI", fmtRsi(ctx.weekly_rsi)]);
  if (ctx.monthly_rsi != null) items.push(["Monthly RSI", fmtRsi(ctx.monthly_rsi)]);
  if (ctx.divergence_timeframe) items.push(["Signal TF", ctx.divergence_timeframe]);
  if (ctx.signal_date) items.push(["Signal Date", new Date(ctx.signal_date).toLocaleDateString("en-IN")]);
  return items;
}

const iconProps = { width: 16, height: 16, viewBox: "0 0 16 16", fill: "none", stroke: "currentColor", strokeWidth: 1.5, "aria-hidden": true } as const;
function CandlesIcon() {
  return (
    <svg {...iconProps}>
      <path d="M4.5 1.5v2M4.5 10.5v4M11.5 1.5v4M11.5 11.5v3" strokeLinecap="round" />
      <rect x="2.75" y="3.5" width="3.5" height="7" rx="0.75" />
      <rect x="9.75" y="5.5" width="3.5" height="6" rx="0.75" fill="currentColor" />
    </svg>
  );
}
function LineIcon() {
  return (
    <svg {...iconProps}>
      <path d="M1.5 12l4-4.5 3 2.5 6-7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
function FitIcon() {
  return (
    <svg {...iconProps}>
      <path d="M1.5 5.5v-4h4M14.5 5.5v-4h-4M1.5 10.5v4h4M14.5 10.5v4h-4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function TradingViewChart({ symbol, signalContext, isMaximized, onToggleMaximize, onClose }: TradingViewChartProps) {
  // Cup Breakout is a MONTHLY detector — open its charts on 1M so the
  // structure markers land on the exact bars the detector used.
  const [timeframe, setTimeframe] = useState<Timeframe>(signalContext?.strategy === "CUP" ? "1M" : "1D");
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
  const contextItems = signalContextItems(signalContext);

  useEffect(() => {
    try {
      localStorage.setItem(INDICATOR_PREFS_STORAGE_KEY, JSON.stringify(indicators));
    } catch {
      // best-effort only
    }
  }, [indicators]);

  const { crosshair, setData, fitContent, bollingerLatest, rsiLatest, paneTops } = useTradingViewChart(containerRef, {
    indicators, chartType, timeframe, cupStructure: signalContext?.cupStructure ?? null,
  });

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
    setData(merged, { fit: false }); // live tick: keep the user's zoom/scroll
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

      {contextItems.length > 0 && (
        <div className="chart-signal-context">
          {contextItems.map(([label, value]) => (
            <span key={label}>{label} <strong>{value}</strong></span>
          ))}
        </div>
      )}

      <div className="chart-panel-body">
        <div className="chart-toolbar">
          <TimeframeSelector value={timeframe} onChange={setTimeframe} />
          <div className="chart-toolbar-right">
            <div className="chart-type-toggle" role="group" aria-label="Chart type">
              <button
                type="button"
                title="Candles"
                aria-label="Candles"
                aria-pressed={chartType === "candles"}
                className={chartType === "candles" ? "chart-toolbar-btn chart-icon-btn active" : "chart-toolbar-btn chart-icon-btn"}
                onClick={() => setChartType("candles")}
              >
                <CandlesIcon />
              </button>
              <button
                type="button"
                title="Line"
                aria-label="Line"
                aria-pressed={chartType === "line"}
                className={chartType === "line" ? "chart-toolbar-btn chart-icon-btn active" : "chart-toolbar-btn chart-icon-btn"}
                onClick={() => setChartType("line")}
              >
                <LineIcon />
              </button>
            </div>
            <IndicatorsMenu value={indicators} onChange={setIndicators} />
            <button type="button" className="chart-toolbar-btn chart-icon-btn" title="Fit all bars" aria-label="Fit all bars" onClick={fitContent}>
              <FitIcon />
            </button>
          </div>
        </div>

        <div className="chart-canvas-wrap">
          {/* Price pane legend */}
          <div className="chart-legend-overlay">
            <span className="chart-legend-title">
              {symbol} <span className="muted">· {timeframe}</span>
              {crosshair && !crosshair.isLatest && <span className="muted"> · {fmtLegendTime(crosshair.time, timeframe)}</span>}
            </span>
            <OHLCReadout readout={crosshair} showVolume={!indicators.volume} />
            {indicators.bollinger && bollingerLatest && (
              <span className="chart-indicator-legend">
                BB {indicators.bollingerPeriod} {indicators.bollingerMultiplier}{" "}
                <span className="bb-upper-lower">{bollingerLatest.upper.toFixed(2)}</span>{" "}
                <span className="bb-mid">{bollingerLatest.middle.toFixed(2)}</span>{" "}
                <span className="bb-upper-lower">{bollingerLatest.lower.toFixed(2)}</span>
              </span>
            )}
          </div>
          {/* In-pane legends: each indicator's name/value sits inside its own pane. */}
          {indicators.volume && paneTops.volume !== null && (
            <div className="chart-pane-legend" style={{ top: paneTops.volume + 4 }}>
              Vol <strong>{fmtVolume(crosshair?.volume ?? null)}</strong>
            </div>
          )}
          {indicators.rsi && paneTops.rsi !== null && (
            <div className="chart-pane-legend" style={{ top: paneTops.rsi + 4 }}>
              RSI {indicators.rsiPeriod} <strong className="rsi-value">{fmtRsi(crosshair?.rsi ?? rsiLatest)}</strong>
            </div>
          )}
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

