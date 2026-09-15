from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field


class FutureContractOut(BaseModel):
    underlying: str
    trading_symbol: str
    token: str
    exch_seg: str
    expiry: str
    is_index: bool
    lot_size: int


class PricePointOut(BaseModel):
    date: dt.datetime
    close: float


class LevelPointOut(BaseModel):
    date: dt.datetime
    value: float


class BacktestRequest(BaseModel):
    symbol: str
    instrument_type: str = "EQUITY"  # "EQUITY" (NSE cash) or "FUTURES" (NFO)
    expiry: str | None = None  # ISO date; None = nearest/current contract
    timeframe: str = "1D"
    from_date: dt.datetime
    to_date: dt.datetime
    starting_capital: float = Field(default=100.0, gt=0)


class SignalOut(BaseModel):
    direction: str
    signal_date: dt.datetime
    system_point: float
    entry_price: float
    reversal_event_id: str | None


class TradeOut(BaseModel):
    trade_number: int
    direction: str
    symbol: str
    trading_symbol: str
    expiry: str
    signal_date: dt.datetime
    entry_date: dt.datetime
    entry_price: float
    system_point: float
    initial_sl: float
    active_stop: float
    reversal_event_id: str
    lot_size: int
    exit_date: dt.datetime | None
    exit_price: float | None
    exit_reason: str | None
    pnl_points: float | None
    pnl_amount: float | None
    pnl_pct: float | None
    holding_days: int | None
    status: str


class EquityPointOut(BaseModel):
    date: dt.datetime
    trade_number: int
    equity: float
    cumulative_pnl_pct: float
    drawdown_pct: float


class StatisticsOut(BaseModel):
    total_signals: int
    buy_signals: int
    sell_signals: int
    total_trades: int
    buy_trades: int
    sell_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    gross_profit_pct: float
    gross_loss_pct: float
    net_pnl_pct: float
    average_trade_pct: float
    average_win_pct: float
    average_loss_pct: float
    best_trade_pct: float
    worst_trade_pct: float
    profit_factor: float | None
    max_drawdown_pct: float
    average_holding_days: float
    expectancy_pct: float


class DataCoverageOut(BaseModel):
    requested_from: dt.datetime
    requested_to: dt.datetime
    available_from: dt.datetime | None
    available_to: dt.datetime | None
    is_complete: bool


class BacktestResultOut(BaseModel):
    backtest_id: str
    symbol: str
    trading_symbol: str
    expiry: str
    instrument_class: str
    exch_seg: str
    timeframe: str
    starting_capital: float
    coverage: DataCoverageOut
    statistics: StatisticsOut
    price_series: list[PricePointOut]
    system_point_line: list[LevelPointOut]
    stop_loss_line: list[LevelPointOut]
    trades: list[TradeOut]
    signals: list[SignalOut]
    equity_curve: list[EquityPointOut]
    created_at: dt.datetime
