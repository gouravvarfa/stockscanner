export type Timeframe = "1m" | "5m" | "15m" | "30m" | "1H" | "4H" | "1D" | "1W" | "1M";

export const TIMEFRAMES: Timeframe[] = ["1m", "5m", "15m", "30m", "1H", "4H", "1D", "1W", "1M"];

export interface OHLCBar {
  /** Unix seconds (UTC) — matches lightweight-charts' UTCTimestamp. */
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

export interface IndicatorSettings {
  rsi: boolean;
  rsiPeriod: number;
  rsiUpper: number;
  rsiLower: number;
  bollinger: boolean;
  bollingerPeriod: number;
  bollingerMultiplier: number;
  volume: boolean;
}

export const DEFAULT_INDICATOR_SETTINGS: IndicatorSettings = {
  rsi: true,
  rsiPeriod: 14,
  rsiUpper: 60,
  rsiLower: 40,
  bollinger: false,
  bollingerPeriod: 20,
  bollingerMultiplier: 2,
  volume: true,
};

export type ChartDataStatus = "loading" | "ready" | "empty" | "error";

/** Scanner-derived context shown in the chart panel header — display only, never fed back into strategy logic. */
export interface ChartSignalContext {
  strategy: string;
  daily_rsi: number | null;
  weekly_rsi: number | null;
  monthly_rsi: number | null;
  signal_date: string | null;
  divergence_timeframe?: string | null;
  explanation?: string;
}

export interface ChartState {
  isOpen: boolean;
  symbol: string | null;
  isMaximized: boolean;
  signalContext: ChartSignalContext | null;
}
