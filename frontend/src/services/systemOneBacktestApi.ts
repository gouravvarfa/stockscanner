const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

export interface SystemOneTrade {
  trade_number: number;
  signal_date: string;
  entry_date: string;
  entry_price: number;
  stop_loss: number;
  risk_per_share: number;
  risk_per_trade: number;
  quantity: number;
  exit_price: number | null;
  exit_date: string | null;
  pnl_amount: number | null;
  status: "OPEN" | "CLOSED";
  exit_reason: "STOP_AT_MA" | "GAP_OPEN_BELOW_MA" | "OPEN";
  holding_periods: number;
  pnl_pct: number | null;
  r_multiple: number | null;
  unrealized_pnl: number | null;
  data_flag: string;
}

export interface SystemOneYear {
  year: number;
  trades: number;
  wins: number;
  losses: number;
  gross_profit: number;
  gross_loss: number;
  net_pnl: number;
}

export interface SystemOneEquityPoint {
  date: string;
  trade_number: number;
  cumulative_pnl: number;
}

export interface SystemOneCandle {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  rsi: number | null;
  ma: number | null;
}

export interface SystemOneSkippedSignal {
  signal_date: string;
  reason: string;
}

export interface SystemOneBacktest {
  backtest_id: string;
  symbol: string;
  trading_symbol: string;
  timeframe: string;
  from_date: string;
  to_date: string;
  data_available_from: string;
  data_available_to: string;
  reference_capital: number;
  risk_per_trade: number;
  summary: {
    total_trades: number;
    closed_trades: number;
    open_trades: number;
    winning_trades: number;
    losing_trades: number;
    net_realized_pnl: number;
    win_rate: number | null;
    average_win: number | null;
    average_loss: number | null;
    profit_factor: number | null;
    best_trade: number | null;
    worst_trade: number | null;
    max_drawdown: number;
    longest_losing_streak: number;
    unrealized_pnl: number;
  };
  trades: SystemOneTrade[];
  candles: SystemOneCandle[];
  skipped_signals: SystemOneSkippedSignal[];
  yearly: SystemOneYear[];
  equity_curve: SystemOneEquityPoint[];
  warnings: string[];
  note: string;
  created_at: string;
}

export async function runSystemOneBacktest(req: {
  symbol: string;
  timeframe: string;
  from_date: string;
  to_date: string;
}): Promise<SystemOneBacktest> {
  const res = await fetch(`${API_BASE}/api/system-one/backtest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const body = await res.text();
    let detail: string | undefined;
    try {
      detail = (JSON.parse(body) as { detail?: string }).detail;
    } catch {
      // not JSON
    }
    throw new Error(detail ?? `Backtest failed: ${res.status} ${body}`);
  }
  return res.json() as Promise<SystemOneBacktest>;
}

export function systemOneExportUrl(id: string): string {
  return `${API_BASE}/api/system-one/backtest/${id}/export`;
}
