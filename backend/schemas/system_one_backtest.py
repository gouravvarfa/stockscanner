from __future__ import annotations

import datetime as dt

from pydantic import BaseModel


class SystemOneBacktestRequest(BaseModel):
    symbol: str
    from_date: dt.datetime
    to_date: dt.datetime


class SystemOneTradeOut(BaseModel):
    trade_number: int
    signal_date: dt.datetime
    entry_date: dt.datetime
    entry_price: float
    stop_loss: float
    risk_per_share: float
    risk_per_trade: float
    quantity: int
    exit_price: float | None
    exit_date: dt.datetime | None
    pnl_amount: float | None  # None for an OPEN trade — never a fabricated 0
    status: str  # "OPEN" | "CLOSED"


class SystemOneSkippedOut(BaseModel):
    signal_date: dt.datetime
    reason: str


class SystemOneSummaryOut(BaseModel):
    total_trades: int
    closed_trades: int
    open_trades: int
    winning_trades: int
    losing_trades: int
    net_realized_pnl: float
    win_rate: float | None
    average_win: float | None
    average_loss: float | None
    profit_factor: float | None
    best_trade: float | None
    worst_trade: float | None


class SystemOneCandleOut(BaseModel):
    date: dt.datetime
    open: float
    high: float
    low: float
    close: float
    rsi: float | None
    ma: float | None


class SystemOneBacktestOut(BaseModel):
    backtest_id: str
    symbol: str
    trading_symbol: str
    timeframe: str
    from_date: dt.datetime
    to_date: dt.datetime
    data_available_from: dt.datetime
    data_available_to: dt.datetime
    reference_capital: float
    risk_per_trade: float
    summary: SystemOneSummaryOut
    trades: list[SystemOneTradeOut]
    candles: list[SystemOneCandleOut]
    skipped_signals: list[SystemOneSkippedOut]
    warnings: list[str]
    note: str
    created_at: dt.datetime
