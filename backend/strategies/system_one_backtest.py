"""
System One trade backtest (any single timeframe: 1H, 4H, 1D or 1W).

This is separate from the System One *screener* in strategy_one.py (weekly /
monthly RSI band) — that one only says "does this stock qualify today"; this
one simulates the actual trades. Pure logic only: no network, no I/O, so it
can be tested with fixed candles.

Rules (all on the SAME candle series, whatever its timeframe):
  * Signal      : RSI(14) freshly crosses above 60 — previous candle's RSI <= 60
                  and this candle's RSI > 60.
  * Entry       : the CLOSE of the candle AFTER the signal candle.
  * Stop loss   : the 20-period SMA on the entry candle, saved once at entry
                  (never overwritten by later MA values).
  * Risk/share  : entry price - stop loss.
  * Quantity    : floor(risk per trade / risk per share), whole shares.
  * Exit        : first candle after the entry candle whose LOW touches the
                  saved stop loss; exit price is the stop. If the candle OPENS
                  at/below the stop (gap), exit price is the open (real loss
                  can then exceed the planned risk).
  * No exit before the data ends -> the trade stays OPEN (no exit price, no
    realised P&L).
  * One trade at a time: signals while a trade is open are ignored.
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field

import pandas as pd

from backend.config.strategy_config import DEFAULT_SYSTEM_ONE_BACKTEST_CONFIG, SystemOneBacktestConfig
from backend.indicators.moving_averages import sma
from backend.indicators.rsi import rsi

# Guards floor() against float noise such as 99999.99999999999 for 10000/0.1.
_FLOOR_EPSILON = 1e-9


@dataclass
class SystemOneTrade:
    trade_number: int
    signal_date: pd.Timestamp
    entry_date: pd.Timestamp
    entry_price: float
    stop_loss: float  # 20 SMA at entry, frozen
    risk_per_share: float
    risk_per_trade: float
    quantity: int
    status: str  # "OPEN" or "CLOSED"
    exit_date: pd.Timestamp | None = None
    exit_price: float | None = None
    pnl_amount: float | None = None  # gross, closed trades only


@dataclass
class SkippedSignal:
    signal_date: pd.Timestamp
    reason: str


@dataclass
class SystemOneSummary:
    total_trades: int
    closed_trades: int
    open_trades: int
    winning_trades: int
    losing_trades: int
    net_realized_pnl: float  # closed trades only
    # The fields below are all about CLOSED trades; None when there is nothing
    # to compute them from (never a fabricated 0).
    win_rate: float | None = None  # percent of closed trades that made money
    average_win: float | None = None
    average_loss: float | None = None  # negative number
    profit_factor: float | None = None  # gross profit / gross loss; None without a loss
    best_trade: float | None = None
    worst_trade: float | None = None


@dataclass
class SeriesPoint:
    """One candle plus the indicator values the strategy used on it —
    exactly what the chart draws, so the chart can never disagree with the
    trades."""
    date: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    rsi: float | None
    ma: float | None


@dataclass
class SystemOneBacktestResult:
    trades: list[SystemOneTrade] = field(default_factory=list)
    skipped: list[SkippedSignal] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    candles_used: int = 0
    series: list[SeriesPoint] = field(default_factory=list)  # candles inside the requested window

    def summary(self) -> SystemOneSummary:
        closed = [t for t in self.trades if t.status == "CLOSED"]
        pnls = [t.pnl_amount for t in closed if t.pnl_amount is not None]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        return SystemOneSummary(
            total_trades=len(self.trades),
            closed_trades=len(closed),
            open_trades=len(self.trades) - len(closed),
            winning_trades=len(wins),
            losing_trades=len(losses),
            net_realized_pnl=float(sum(pnls)),
            win_rate=len(wins) / len(pnls) * 100.0 if pnls else None,
            average_win=sum(wins) / len(wins) if wins else None,
            average_loss=sum(losses) / len(losses) if losses else None,
            profit_factor=sum(wins) / -sum(losses) if losses else None,
            best_trade=max(pnls) if pnls else None,
            worst_trade=min(pnls) if pnls else None,
        )


def _is_missing(value: float) -> bool:
    return value is None or math.isnan(value)


def run_system_one_backtest(
    ohlcv: pd.DataFrame,
    config: SystemOneBacktestConfig = DEFAULT_SYSTEM_ONE_BACKTEST_CONFIG,
    from_date: dt.datetime | None = None,
    to_date: dt.datetime | None = None,
) -> SystemOneBacktestResult:
    """
    `ohlcv`: candles of one timeframe, DatetimeIndex ascending, with a "close" column.

    Candles before `from_date` are used only to warm up RSI and the 20 SMA —
    a signal is accepted only if its own candle is on/after `from_date`.
    Candles after `to_date` are dropped, so "end of data" means `to_date`.
    """
    result = SystemOneBacktestResult()
    if ohlcv is None or ohlcv.empty or "close" not in ohlcv.columns:
        result.warnings.append("No candle data available.")
        return result

    df = ohlcv.sort_index()
    if to_date is not None:
        df = df.loc[df.index <= to_date]
    result.candles_used = len(df)

    min_candles = max(config.rsi_period + 2, config.ma_period + 1)
    if len(df) < min_candles:
        result.warnings.append(
            f"Insufficient history: need at least {min_candles} candles, found {len(df)}."
        )
        return result

    dates = list(df.index)
    closes = df["close"].astype(float).tolist()
    rsi_values = rsi(df["close"].astype(float), period=config.rsi_period).astype(float).tolist()
    ma_values = sma(df["close"].astype(float), config.ma_period).astype(float).tolist()

    n = len(df)
    risk_per_trade = config.risk_per_trade

    def _col(name: str) -> list[float]:
        return df[name].astype(float).tolist() if name in df.columns else closes

    opens, highs, lows = _col("open"), _col("high"), _col("low")
    result.series = [
        SeriesPoint(
            date=dates[k], open=opens[k], high=highs[k], low=lows[k], close=closes[k],
            rsi=None if _is_missing(rsi_values[k]) else rsi_values[k],
            ma=None if _is_missing(ma_values[k]) else ma_values[k],
        )
        for k in range(n)
        if from_date is None or dates[k] >= from_date
    ]
    i = 1
    while i < n:
        if from_date is not None and dates[i] < from_date:
            i += 1
            continue

        prev_rsi, cur_rsi = rsi_values[i - 1], rsi_values[i]
        crossed_up = (
            not _is_missing(prev_rsi) and not _is_missing(cur_rsi)
            and prev_rsi <= config.rsi_entry_level < cur_rsi
        )
        if not crossed_up:
            i += 1
            continue

        signal_idx = i
        entry_idx = signal_idx + 1
        if entry_idx >= n:
            result.skipped.append(SkippedSignal(dates[signal_idx], "No next candle yet to enter on (signal on the last candle)."))
            break

        entry_price = closes[entry_idx]
        stop_loss = ma_values[entry_idx]
        if _is_missing(stop_loss):
            result.skipped.append(SkippedSignal(dates[signal_idx], "20 MA not available on the entry candle."))
            i += 1
            continue
        if entry_price <= stop_loss:
            result.skipped.append(SkippedSignal(
                dates[signal_idx],
                f"Entry price {entry_price:.2f} is not above the 20 MA {stop_loss:.2f}; risk per share would be zero or negative.",
            ))
            i += 1
            continue

        risk_per_share = entry_price - stop_loss
        quantity = math.floor(risk_per_trade / risk_per_share + _FLOOR_EPSILON)
        if quantity < 1:
            result.skipped.append(SkippedSignal(
                dates[signal_idx],
                f"Quantity would be 0: risk per share {risk_per_share:.2f} is above the risk per trade {risk_per_trade:.2f}.",
            ))
            i += 1
            continue

        trade = SystemOneTrade(
            trade_number=len(result.trades) + 1,
            signal_date=dates[signal_idx],
            entry_date=dates[entry_idx],
            entry_price=entry_price,
            stop_loss=stop_loss,
            risk_per_share=risk_per_share,
            risk_per_trade=risk_per_trade,
            quantity=quantity,
            status="OPEN",
        )

        # Stop hit: the candle's low reaches the frozen stop. If the candle opens
        # at/below the stop (a gap) we cannot get the stop price, so exit at the open.
        exit_idx = None
        exit_price = None
        for j in range(entry_idx + 1, n):
            if opens[j] <= stop_loss:
                exit_idx, exit_price = j, opens[j]
                break
            if lows[j] <= stop_loss:
                exit_idx, exit_price = j, stop_loss
                break

        if exit_idx is not None:
            trade.status = "CLOSED"
            trade.exit_date = dates[exit_idx]
            trade.exit_price = exit_price
            trade.pnl_amount = (trade.exit_price - entry_price) * quantity

        result.trades.append(trade)
        # Closed: look for the next signal after the exit candle. Open: nothing left to scan.
        i = exit_idx + 1 if exit_idx is not None else n

    return result
