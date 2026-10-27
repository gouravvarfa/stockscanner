"""
System One trade backtest (any single timeframe: 1H, 4H, 1D or 1W).

This is separate from the System One *screener* in strategy_one.py (weekly /
monthly RSI band) — that one only says "does this stock qualify today"; this
one simulates the actual trades. Pure logic only: no network, no I/O, so it
can be tested with fixed candles.

Rules (all on the SAME candle series, whatever its timeframe):
  * Signal      : RSI(14) freshly crosses above 60 - previous candle's RSI <= 60
                  and this candle's RSI > 60.
  * Entry       : the CLOSE of the candle AFTER the signal candle.
  * Initial stop: the 20-period SMA on the entry candle. Used for position
                  sizing; entry price <= that MA means the signal is skipped.
  * Risk/share  : entry price - initial stop.
  * Quantity    : floor(risk per trade / risk per share), whole shares.
  * Exit        : for every candle j after the entry candle the stop level is
                  the PREVIOUS candle's (j-1) 20 SMA - already known at j's open,
                  so no look-ahead. If j OPENS below it: exit at j's open
                  (GAP_OPEN_BELOW_MA). Else if j's LOW touches/breaks it: exit
                  at the stop level (STOP_AT_MA). A candle holds both its low
                  and high but not their order; a touched stop is assumed hit.
  * No exit before the data ends -> the trade stays OPEN (no exit price, no
    realised P&L); its unrealised P&L uses the last candle's close.
  * One trade at a time: signals while a trade is open are ignored; the next
    signal is looked for from the candle after the exit candle.
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
    exit_reason: str = "OPEN"  # STOP_AT_MA | GAP_OPEN_BELOW_MA | OPEN
    holding_periods: int = 0  # candles held (to the exit, or to the last candle while open)
    pnl_pct: float | None = None  # pnl as % of entry price, closed trades only
    r_multiple: float | None = None  # pnl / planned risk per trade, closed trades only
    unrealized_pnl: float | None = None  # open trades only: last candle close vs entry
    data_flag: str = ""


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
    max_drawdown: float = 0.0  # Rs, peak-to-trough of cumulative realised P&L (positive number)
    longest_losing_streak: int = 0
    unrealized_pnl: float = 0.0  # open trades only, NOT part of net_realized_pnl


@dataclass
class YearRow:
    year: int  # the year the trades EXITED in
    trades: int
    wins: int
    losses: int
    gross_profit: float
    gross_loss: float  # negative number
    net_pnl: float


@dataclass
class EquityPoint:
    date: pd.Timestamp
    trade_number: int
    cumulative_pnl: float


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
            max_drawdown=self._max_drawdown(),
            longest_losing_streak=self._longest_losing_streak(),
            unrealized_pnl=float(sum(t.unrealized_pnl for t in self.trades if t.unrealized_pnl is not None)),
        )

    def _closed_by_exit(self) -> list[SystemOneTrade]:
        return sorted(
            (t for t in self.trades if t.status == "CLOSED" and t.pnl_amount is not None),
            key=lambda t: (t.exit_date, t.trade_number),
        )

    def equity_curve(self) -> list[EquityPoint]:
        total, points = 0.0, []
        for t in self._closed_by_exit():
            total += t.pnl_amount
            points.append(EquityPoint(t.exit_date, t.trade_number, total))
        return points

    def _max_drawdown(self) -> float:
        peak, worst = 0.0, 0.0
        for p in self.equity_curve():
            peak = max(peak, p.cumulative_pnl)
            worst = max(worst, peak - p.cumulative_pnl)
        return worst

    def _longest_losing_streak(self) -> int:
        best = run = 0
        for t in self._closed_by_exit():
            run = run + 1 if t.pnl_amount < 0 else 0
            best = max(best, run)
        return best

    def yearly(self) -> list[YearRow]:
        by_year: dict[int, list[float]] = {}
        for t in self._closed_by_exit():
            by_year.setdefault(t.exit_date.year, []).append(t.pnl_amount)
        return [
            YearRow(
                year=y, trades=len(p), wins=sum(1 for x in p if x > 0), losses=sum(1 for x in p if x < 0),
                gross_profit=float(sum(x for x in p if x > 0)), gross_loss=float(sum(x for x in p if x < 0)),
                net_pnl=float(sum(p)),
            )
            for y, p in sorted(by_year.items())
        ]


def find_data_gaps(index: pd.DatetimeIndex, max_days: int) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """(last candle before, first candle after) for every hole wider than `max_days`.
    Nothing is filled in; the caller reports the hole as a DATA GAP."""
    return [(a, b) for a, b in zip(index[:-1], index[1:]) if (b - a).days > max_days]


def flag_trades_in_gaps(result: SystemOneBacktestResult, gaps: list[tuple[pd.Timestamp, pd.Timestamp]]) -> None:
    last = result.series[-1].date if result.series else None
    for t in result.trades:
        end = t.exit_date if t.exit_date is not None else last
        if end is not None and any(t.entry_date <= after and end >= before for before, after in gaps):
            t.data_flag = ("DATA GAP inside this trade. " + t.data_flag).strip()


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

        # Stop for candle j is the PREVIOUS candle's 20 SMA (known at j's open).
        exit_idx = None
        exit_price = None
        exit_reason = "OPEN"
        for j in range(entry_idx + 1, n):
            stop_level = ma_values[j - 1]
            if _is_missing(stop_level):
                continue
            if opens[j] < stop_level:
                exit_idx, exit_price, exit_reason = j, opens[j], "GAP_OPEN_BELOW_MA"
                break
            if lows[j] <= stop_level:
                exit_idx, exit_price, exit_reason = j, stop_level, "STOP_AT_MA"
                break

        if exit_idx is not None:
            trade.status = "CLOSED"
            trade.exit_date = dates[exit_idx]
            trade.exit_price = exit_price
            trade.exit_reason = exit_reason
            trade.holding_periods = exit_idx - entry_idx
            trade.data_flag = (
                "Low-vs-High order inside the candle is unknown; a touched stop is assumed hit"
                if exit_reason == "STOP_AT_MA" else "Gap fill at the candle's open"
            )
            trade.pnl_amount = (trade.exit_price - entry_price) * quantity
            trade.pnl_pct = (trade.exit_price - entry_price) / entry_price * 100.0
            trade.r_multiple = trade.pnl_amount / risk_per_trade
        else:
            trade.holding_periods = n - 1 - entry_idx
            trade.unrealized_pnl = (closes[n - 1] - entry_price) * quantity

        result.trades.append(trade)
        # Closed: look for the next signal after the exit candle. Open: nothing left to scan.
        i = exit_idx + 1 if exit_idx is not None else n

    return result
