/** Timeframes the System One backtest supports (the backend validates the same list). */
export const SYSTEM_ONE_TIMEFRAMES = [
  { value: "1H", label: "1H", noun: "hourly" },
  { value: "4H", label: "4H", noun: "4-hour" },
  { value: "1D", label: "1D", noun: "daily" },
  { value: "1W", label: "1W", noun: "weekly" },
] as const;

export const DEFAULT_TIMEFRAME = "1W";

export function isIntraday(timeframe: string): boolean {
  return timeframe === "1H" || timeframe === "4H";
}

export function timeframeNoun(timeframe: string): string {
  return SYSTEM_ONE_TIMEFRAMES.find((t) => t.value === timeframe)?.noun ?? timeframe;
}
