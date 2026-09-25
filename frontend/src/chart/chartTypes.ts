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
/**
 * The exact Cup structure the backend detector selected
 * (backend/strategies/cup.py detect_cup) — drawn on the chart as-is, never
 * re-derived in the frontend, so the markers always match what the scanner
 * actually reported. Dates are the backend's monthly period-end ISO dates.
 */
export interface CupStructure {
  trend_start_date?: string | null;
  trend_start_price?: number | null;
  left_rim_date: string | null;
  left_rim_price: number | null;
  cup_bottom_date: string | null;
  cup_bottom_price: number | null;
  right_rim_date?: string | null;
  right_rim_price?: number | null;
  breakout_level: number | null;
  breakout_date?: string | null;
  handle_start_date?: string | null;
  handle_end_date?: string | null;
  handle_low_price?: number | null;
}

export interface ChartSignalContext {
  strategy: string;
  daily_rsi: number | null;
  weekly_rsi: number | null;
  monthly_rsi: number | null;
  signal_date: string | null;
  divergence_timeframe?: string | null;
  explanation?: string;
  cupStructure?: CupStructure | null;
}

export interface ChartState {
  isOpen: boolean;
  symbol: string | null;
  isMaximized: boolean;
  signalContext: ChartSignalContext | null;
}
