const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text();
    let detail: string | undefined;
    try {
      detail = (JSON.parse(body) as { detail?: string }).detail;
    } catch {
      // not JSON — no `detail` to extract, fall through to the raw message below
    }
    throw new Error(detail ?? `API ${path} failed: ${res.status} ${body}`);
  }
  return res.json() as Promise<T>;
}

export interface TimeframeReading {
  rsi: number | null;
  has_bearish_divergence: boolean;
  divergence_count: number;
}

export interface FibonacciOut {
  swing_high: number;
  swing_low: number;
  direction: string;
  nearest_ratio: number;
  nearest_price: number;
  distance_pct: number;
  in_preferred_zone: boolean;
}

export interface TradeSetupOut {
  available: boolean;
  reason: string | null;
  entry_low: number | null;
  entry_high: number | null;
  stop_loss: number | null;
  target1: number | null;
  target2: number | null;
  risk_reward_t1: number | null;
  risk_reward_t2: number | null;
  methodology: string;
}

export interface StockResult {
  rank: number;
  symbol: string;
  sector: string;
  current_price: number;
  data_as_of: string;
  score: number;
  classification: string;
  bias: string;
  components: Record<string, number>;
  daily: TimeframeReading;
  weekly: TimeframeReading;
  monthly: TimeframeReading;
  fibonacci: FibonacciOut | null;
  ema20: number | null;
  ema50: number | null;
  ema200: number | null;
  macd_histogram: number | null;
  adx: number | null;
  volume_ratio: number | null;
  distance_from_52w_high_pct: number | null;
  meets_weekly_rsi_band: boolean;
  meets_monthly_rsi_min: boolean;
  disqualified_by_divergence: boolean;
  explanation: string[];
  data_warnings: string[];
  trade_setup: TradeSetupOut | null;
}

export interface SectorResult {
  sector: string;
  nse_index: string | null;
  available: boolean;
  unavailable_reason: string | null;
  daily_rsi: number | null;
  weekly_rsi: number | null;
  monthly_rsi: number | null;
  daily_return_pct: number | null;
  weekly_return_pct: number | null;
  monthly_return_pct: number | null;
  daily_vs_nifty: number | null;
  weekly_vs_nifty: number | null;
  monthly_vs_nifty: number | null;
  meets_rsi_thresholds: boolean;
  outperforms_nifty: boolean;
  sector_score: number;
  weekly_data_source?: string;
  monthly_data_source?: string;
}

export interface StrategySignal {
  strategy: string;
  symbol: string;
  sector: string;
  qualifies: boolean;
  signal_date: string | null;
  daily_rsi: number | null;
  weekly_rsi: number | null;
  monthly_rsi: number | null;
  conditions: Record<string, boolean>;
  explanation: string;
  extra: Record<string, unknown>;
}

export interface StrategyDescriptor {
  name: string;
  description: string;
}

export const STRATEGY_NAMES = [
  "Strategy One",
  "GFS",
  "Advanced GFS",
  "PRD",
  "NRD",
  "Value Buy",
] as const;
export type StrategyName = (typeof STRATEGY_NAMES)[number];

export interface ScanResult {
  scan_id: number | null;
  started_at: string;
  finished_at: string;
  execution_seconds: number;
  data_source: string;
  universe_requested: number;
  universe_returned: number;
  universe_complete: boolean;
  universe_note: string | null;
  stocks_scanned: number;
  stocks_failed: number;
  failed_symbols: string[];
  qualifying_sectors: string[];
  sectors: SectorResult[];
  top10: StockResult[];
  top3: StockResult[];
  best: StockResult | null;
  strategies: Record<string, StrategySignal[]>;
  errors: string[];
}

export interface ScanRunSummary {
  id: number;
  scan_type: string;
  started_at: string;
  finished_at: string | null;
  execution_seconds: number | null;
  stocks_scanned: number;
  stocks_failed: number;
  qualifying_sectors: number;
  qualifying_stocks: number;
  universe_requested: number;
  universe_returned: number;
  universe_complete: boolean;
}

export interface StrategyConfig {
  sector_rsi: { daily_min: number; weekly_min: number; monthly_min: number };
  stock_rsi: {
    weekly_min: number;
    weekly_max: number;
    monthly_min: number;
    daily_confirmation_enabled: boolean;
    daily_min: number;
    daily_max: number;
  };
  divergence: {
    swing_lookback: number;
    min_price_difference_pct: number;
    min_rsi_difference: number;
    confirmation_candles: number;
    strict_mode: boolean;
  };
  fibonacci: {
    levels: number[];
    preferred_zones: number[];
    zone_tolerance_pct: number;
    swing_lookback_bars: number;
  };
  trend: {
    ema_fast: number;
    ema_medium: number;
    ema_slow: number;
    adx_period: number;
    adx_healthy_min: number;
    volume_avg_period: number;
    volume_ratio_min: number;
  };
  weights: Record<string, number>;
  classification: { strong_setup_min: number; good_setup_min: number; moderate_setup_min: number };
}

export interface ExpiryLevel1Signal {
  symbol: string;
  instrument_type: "INDEX" | "STOCK";
  name: string;
  sector: string | null;
  signal_date: string;
  rsi_15m: number;
  rsi_15m_prev: number;
  rsi_1h: number;
  status: string;
  strategy: string;
  explanation: string;
}

export interface ExpiryLevel1Result {
  started_at: string;
  finished_at: string;
  execution_seconds: number;
  angelone_configured: boolean;
  symbols_scanned: number;
  symbols_failed: number;
  failed_symbols: string[];
  index_signals: ExpiryLevel1Signal[];
  stock_signals: ExpiryLevel1Signal[];
  errors: string[];
}

export interface ExpiryLevel1Config {
  rsi_15m_min: number;
  rsi_15m_max: number;
  rsi_1h_threshold: number;
  rsi_period: number;
  intraday_lookback_days: number;
}

export interface AngelOneStatus {
  configured: boolean;
  client_code: string | null;
  message: string;
}

export interface AngelOneConnectRequest {
  api_key: string;
  client_code: string;
  pin: string;
  totp_secret: string;
}

export interface ExpiryLevel5Candle {
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface ExpiryLevel5Signal {
  strategy: string;
  signal: string;
  symbol: string;
  instrument_type: string;
  signal_date: string;
  swing_high: number;
  swing_low: number;
  fib_38_2: number | null;
  fib_50: number | null;
  fib_61_8: number;
  support_price: number;
  support_confirmed: boolean;
  confirmation_candle: ExpiryLevel5Candle;
  previous_candle_high: number;
  confirmation_close_above_previous_high: boolean;
  reason: string;
}

export interface ExpiryLevel5Result {
  started_at: string;
  finished_at: string;
  execution_seconds: number;
  angelone_configured: boolean;
  symbols_scanned: number;
  symbols_failed: number;
  failed_symbols: string[];
  signals: ExpiryLevel5Signal[];
  errors: string[];
}

export type DataSourceMode = "auto" | "tapetide" | "angel_one";

export interface DataSourceConfig {
  mode: DataSourceMode;
}

export interface ProviderStatus {
  name: string;
  status: string;
  detail: string | null;
}

export const api = {
  health: () => request<{ status: string }>("/api/health"),
  runScan: (scanType: string = "manual") =>
    request<ScanResult>(`/api/scan/run?scan_type=${scanType}`, { method: "POST" }),
  listHistory: (limit = 20) => request<ScanRunSummary[]>(`/api/history?limit=${limit}`),
  getRun: (id: number) => request<ScanRunSummary>(`/api/history/${id}`),
  getConfig: () => request<StrategyConfig>("/api/config"),
  updateConfig: (config: StrategyConfig) =>
    request<StrategyConfig>("/api/config", { method: "PUT", body: JSON.stringify(config) }),
  resetConfig: () => request<StrategyConfig>("/api/config/reset", { method: "POST" }),
  listStrategies: () => request<StrategyDescriptor[]>("/api/scanner/strategies"),
  runExpiryScan: (maxStocks = 40) =>
    request<ExpiryLevel1Result>(`/api/expiry/scan?max_stocks=${maxStocks}`, { method: "POST" }),
  getExpiryConfig: () => request<ExpiryLevel1Config>("/api/expiry/config"),
  getAngelOneStatus: () => request<AngelOneStatus>("/api/expiry/angelone/status"),
  connectAngelOne: (body: AngelOneConnectRequest) =>
    request<AngelOneStatus>("/api/expiry/angelone/connect", { method: "POST", body: JSON.stringify(body) }),
  disconnectAngelOne: () => request<AngelOneStatus>("/api/expiry/angelone/disconnect", { method: "POST" }),
  runExpiryLevel5Scan: (maxStocks = 40) =>
    request<ExpiryLevel5Result>(`/api/expiry-level-5/scan?max_stocks=${maxStocks}`, { method: "POST" }),
  getExpiryLevel5Config: () => request<Record<string, unknown>>("/api/expiry-level-5/config"),
  getDataSource: () => request<DataSourceConfig>("/api/data-source"),
  updateDataSource: (config: DataSourceConfig) =>
    request<DataSourceConfig>("/api/data-source", { method: "PUT", body: JSON.stringify(config) }),
  getProviderStatus: () => request<ProviderStatus[]>("/api/data-source/providers"),
};
