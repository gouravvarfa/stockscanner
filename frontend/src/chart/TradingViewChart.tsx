import { useEffect, useRef, useState } from "react";
import { fetchCandles } from "./chartDatafeed";
import { IndicatorsMenu } from "./IndicatorsMenu";
import { OHLCReadout } from "./OHLCReadout";
import { TimeframeSelector } from "./TimeframeSelector";
import { DEFAULT_INDICATOR_SETTINGS, type ChartDataStatus, type ChartSignalContext, type IndicatorSettings, type Timeframe } from "./chartTypes";
import { useTradingViewChart } from "./useTradingViewChart";
import { INDICATOR_PREFS_STORAGE_KEY } from "./chartConfig";

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
  const [indicators, setIndicators] = useState<IndicatorSettings>(loadIndicatorPrefs);
  const [status, setStatus] = useState<ChartDataStatus>("loading");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const requestIdRef = useRef(0);

  useEffect(() => {
    try {
      localStorage.setItem(INDICATOR_PREFS_STORAGE_KEY, JSON.stringify(indicators));
    } catch {
      // best-effort only
    }
  }, [indicators]);

  const { crosshair, setData, fitContent, bollingerLatest, rsiLatest } = useTradingViewChart(containerRef, { indicators });

  useEffect(() => {
    const controller = new AbortController();
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setStatus("loading");
    setErrorMessage(null);

    fetchCandles(symbol, timeframe, controller.signal)
      .then((bars) => {
        if (requestIdRef.current !== requestId) return;
        if (bars.length === 0) {
          setStatus("empty");
          return;
        }
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

  return (
    <div className={isMaximized ? "chart-panel chart-panel-maximized" : "chart-panel"}>
      <div className="chart-panel-header">
        <div className="chart-panel-title">
          <strong>{symbol}</strong>
          {signalContext && <span className="chip chip-pass">{signalContext.strategy}</span>}
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

