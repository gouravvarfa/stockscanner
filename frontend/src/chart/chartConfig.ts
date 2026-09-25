export const INDICATOR_PREFS_STORAGE_KEY = "scanner-chart-indicator-prefs";
export const DEFAULT_TIMEFRAME_STORAGE_KEY = "scanner-chart-default-timeframe";

// Indicator pane heights, as a ratio of the chart's height clamped to a
// readable pixel range — price always keeps the rest (and at least
// MIN_PRICE_PANE_HEIGHT). Pane ORDER is computed at runtime in
// useTradingViewChart (price, then volume if on, then RSI if on), never a
// fixed index, so toggling one indicator can't drop it into the other's pane.
export const VOLUME_PANE_RATIO = 0.12;
export const MIN_VOLUME_PANE_HEIGHT = 64;
export const MAX_VOLUME_PANE_HEIGHT = 100;
export const RSI_PANE_RATIO = 0.2;
export const MIN_RSI_PANE_HEIGHT = 110;
export const MAX_RSI_PANE_HEIGHT = 170;
export const MIN_PRICE_PANE_HEIGHT = 220;
