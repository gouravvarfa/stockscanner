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
      // not JSON
    }
    throw new Error(detail ?? `API ${path} failed: ${res.status} ${body}`);
  }
  return res.json() as Promise<T>;
}

export interface FutureContract {
  underlying: string;
  trading_symbol: string;
  token: string;
  exch_seg: string;
  expiry: string;
  is_index: boolean;
  lot_size: number;
}

export interface TopBottomSignal {
  direction: "BUY" | "SELL";
  signal_date: string;
  system_point: number;
  entry_price: number;
  reversal_event_id: string | null;
}

export interface TopBottomTrade {
  trade_number: number;
  direction: "BUY" | "SELL";
  symbol: string;
  trading_symbol: string;
  expiry: string;
  signal_date: string;
  entry_date: string;
  entry_price: number;
  system_point: number;
  initial_sl: number;
  active_stop: number;
  reversal_event_id: string;
  lot_size: number;
  exit_date: string | null;
  exit_price: number | null;
  exit_reason: "TRAILING_STOP_REVERSAL" | "END_OF_BACKTEST" | null;
  pnl_points: number | null;
  pnl_amount: number | null;
  pnl_pct: number | null;
  holding_days: number | null;
  status: "OPEN" | "WIN" | "LOSS" | "BREAKEVEN";
}

export interface PricePoint {
  date: string;
  close: number;
}

export interface LevelPoint {
  date: string;
  value: number;
}

export interface EquityPoint {
  date: string;
  trade_number: number;
  equity: number;
  cumulative_pnl_pct: number;
  drawdown_pct: number;
}

export interface BacktestStatistics {
  total_signals: number;
  buy_signals: number;
  sell_signals: number;
  total_trades: number;
  buy_trades: number;
  sell_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  gross_profit_pct: number;
  gross_loss_pct: number;
  net_pnl_pct: number;
  average_trade_pct: number;
  average_win_pct: number;
  average_loss_pct: number;
  best_trade_pct: number;
  worst_trade_pct: number;
  profit_factor: number | null;
  max_drawdown_pct: number;
  average_holding_days: number;
  expectancy_pct: number;
}

export interface DataCoverage {
  requested_from: string;
  requested_to: string;
  available_from: string | null;
  available_to: string | null;
  is_complete: boolean;
}

export interface BacktestResult {
  instrument_type?: "FUTURE" | "EQUITY";
  backtest_id: string;
  symbol: string;
  trading_symbol: string;
  expiry: string;
  instrument_class: "STOCK" | "INDEX";
  exch_seg: string;
  timeframe: string;
  starting_capital: number;
  coverage: DataCoverage;
  statistics: BacktestStatistics;
  price_series: PricePoint[];
  system_point_line: LevelPoint[];
  stop_loss_line: LevelPoint[];
  trades: TopBottomTrade[];
  signals: TopBottomSignal[];
  equity_curve: EquityPoint[];
  created_at: string;
}

export interface BacktestRequest {
  symbol: string;
  instrument_type: "EQUITY" | "FUTURES";
  expiry?: string | null;
  timeframe: string;
  from_date: string;
  to_date: string;
  starting_capital: number;
}

export const TOP_BOTTOM_TIMEFRAMES = ["1m", "5m", "15m", "30m", "1H", "4H", "1D", "1W"] as const;

export function searchFutures(query: string): Promise<FutureContract[]> {
  if (!query.trim()) return Promise.resolve([]);
  return request(`/api/top-bottom/futures/search?q=${encodeURIComponent(query.trim())}`);
}

export function searchEquities(query: string): Promise<string[]> {
  if (!query.trim()) return Promise.resolve([]);
  return request(`/api/top-bottom/equity/search?q=${encodeURIComponent(query.trim())}`);
}

export function listContracts(symbol: string): Promise<FutureContract[]> {
  return request(`/api/top-bottom/futures/contracts/${encodeURIComponent(symbol)}`);
}

export function runBacktest(req: BacktestRequest): Promise<BacktestResult> {
  return request(`/api/top-bottom/backtest`, { method: "POST", body: JSON.stringify(req) });
}

export function getBacktest(id: string): Promise<BacktestResult> {
  return request(`/api/top-bottom/backtest/${id}`);
}

export function exportBacktestUrl(id: string): string {
  return `${API_BASE}/api/top-bottom/backtest/${id}/export`;
}
