"""
GFS trade backtest (daily candles).

Separate from the GFS *screener* in gfs.py (which uses its own 38-45 band) —
this one simulates the actual trades. Pure logic only: no network, no I/O.

Rules:
  * Setup  : on a daily candle ALL of these hold -
               monthly RSI(14) > 60, weekly RSI(14) > 60, daily RSI(14) in [38, 45].
  * Signal : the first candle where the setup holds after it did not hold on the
             previous candle (so a stock sitting in the zone gives one signal,
             not one per day).
  * Entry  : the CLOSE of the candle after the signal.
  * Size   : quantity = floor(risk per trade / (entry - initial stop)).
  * Stop   : staged, and it only ever moves UP.
               1. Initial: the lowest low of the last 5 candles, entry candle
                  included (signal skipped if the entry is not above it).
               2. Breakeven: once a candle CLOSES at least 1R above the entry
                  (R = entry - initial stop), the stop moves to the entry price.
               3. Trailing: while the last 3 candles each made a higher low, the
                  stop moves up to the oldest of those 3 lows. In a sideways
                  market (lows flat or falling) the stop stays where it is.
             The stop that applies to a candle is the one known BEFORE it opens.
  * Exit   : the first of -
               - a candle opens below the stop: fill at its open;
               - a candle's low touches the stop: fill at the stop;
               - the completed weekly RSI is below 60 at a candle's close: fill
                 at that close (the setup that justified the trade is gone).
             There is no profit target. One trade at a time.

Weekly/monthly RSI use COMPLETED bars only: on a daily candle the value is that
of the latest weekly/monthly bar already closed, never the one still forming,
so a signal cannot lean on data from the future.
"""
from __future__ import annotations

import datetime as dt
import math

import pandas as pd

from backend.config.strategy_config import (
    DEFAULT_ADVANCED_GFS_BACKTEST_CONFIG,
    DEFAULT_GFS50_BACKTEST_CONFIG,
    Gfs50BacktestConfig,
    DEFAULT_GFS_BACKTEST_CONFIG,
    AdvancedGFSBacktestConfig,
    GFSBacktestConfig,
)
from backend.indicators.resample import to_monthly, to_weekly
from backend.indicators.rsi import rsi
from backend.strategies.system_one_backtest import (
    _FLOOR_EPSILON,
    SeriesPoint,
    SkippedSignal,
    SystemOneBacktestResult,
    SystemOneTrade,
)


def _completed_rsi_on_daily_index(daily: pd.DataFrame, higher: pd.DataFrame, period: int) -> list[float]:
    """RSI of the higher-timeframe bars, carried forward onto each daily candle
    (bars are labelled with their period end, so a bar is only visible on/after
    the day it closed)."""
    if higher.empty:
        return [float("nan")] * len(daily)
    series = rsi(higher["close"].astype(float), period=period).astype(float)
    return series.reindex(daily.index, method="ffill").tolist()


def _bars_with_rsi(bars: pd.DataFrame, period: int, from_date: dt.datetime | None) -> list[SeriesPoint]:
    """Completed weekly/monthly bars with the RSI the setup used, from `from_date` on."""
    if bars.empty:
        return []
    values = rsi(bars["close"].astype(float), period=period).astype(float).tolist()
    return [
        SeriesPoint(
            date=ts, open=float(row.open), high=float(row.high), low=float(row.low), close=float(row.close),
            rsi=None if v != v else v, ma=None,
        )
        for (ts, row), v in zip(bars.iterrows(), values)
        if from_date is None or ts >= from_date
    ]


def _ok(value: float, test) -> bool:
    return value == value and test(value)  # value == value is False for NaN


def _daily_ok(value: float, config: GFSBacktestConfig) -> bool:
    above_min = value > config.daily_rsi_min if config.daily_min_exclusive else value >= config.daily_rsi_min
    return above_min and value <= config.daily_rsi_max


def _rsi_series(df: pd.DataFrame, config: GFSBacktestConfig) -> "tuple[list[float], list[float], list[float]]":
    """Daily RSI, and the completed weekly / monthly RSI carried onto each daily candle."""
    daily_rsi = rsi(df["close"].astype(float), period=config.rsi_period).astype(float).tolist()
    weekly_rsi = _completed_rsi_on_daily_index(df, to_weekly(df), config.rsi_period)
    monthly_rsi = _completed_rsi_on_daily_index(df, to_monthly(df), config.rsi_period)
    return daily_rsi, weekly_rsi, monthly_rsi


def gfs_setup_flags(df: pd.DataFrame, config: GFSBacktestConfig) -> "tuple[list[bool], list[float], list[float], list[float]]":
    """Per daily candle: does the whole setup hold? Also returns the daily, weekly
    and monthly RSI (weekly/monthly = latest COMPLETED bar). Shared by the
    backtest and the all-stocks list so both always apply the same rule."""
    daily_rsi, weekly_rsi, monthly_rsi = _rsi_series(df, config)
    setup = [
        _ok(m, lambda v: v > config.monthly_rsi_min)
        and _ok(w, lambda v: v > config.weekly_rsi_min)
        and _ok(d, lambda v: _daily_ok(v, config))
        for d, w, m in zip(daily_rsi, weekly_rsi, monthly_rsi)
    ]
    return setup, daily_rsi, weekly_rsi, monthly_rsi


def _gfs_setup_signals(df: pd.DataFrame, config: GFSBacktestConfig) -> "tuple[list[bool], list[float]]":
    setup, daily_rsi, _, _ = gfs_setup_flags(df, config)
    flags = [False] + [setup[k] and not setup[k - 1] for k in range(1, len(setup))]
    return flags, daily_rsi


def _initial_stop(lows: list[float], entry_idx: int, candles: int) -> float | None:
    first = entry_idx - (candles - 1)
    return min(lows[first : entry_idx + 1]) if first >= 0 else None


def _manage_trade(
    opens: list[float], lows: list[float], closes: list[float], weekly_rsi: list[float],
    entry_idx: int, entry_price: float, initial_stop: float, config: GFSBacktestConfig,
) -> "tuple[int | None, float | None, str]":
    """Walk the candles after the entry. Returns (exit index, exit price, reason);
    (None, None, "OPEN") if the data ends first. The stop used on candle j was
    set from candles up to j-1, so nothing here looks ahead."""
    risk = entry_price - initial_stop
    stop = initial_stop
    trail = config.trail_candles
    for j in range(entry_idx + 1, len(closes)):
        if opens[j] < stop:
            return j, opens[j], "GAP_OPEN_BELOW_STOP"
        if lows[j] <= stop:
            return j, stop, "STOP_HIT"
        w = weekly_rsi[j]
        if w == w and w < config.weekly_rsi_exit_below:
            return j, closes[j], "WEEKLY_RSI_EXIT"
        # Candle j survived: raise the stop for candle j+1 (never lower it).
        if closes[j] >= entry_price + config.breakeven_r * risk:
            stop = max(stop, entry_price)
        if j >= trail - 1 and all(lows[k] > lows[k - 1] for k in range(j - trail + 2, j + 1)):
            stop = max(stop, lows[j - trail + 1])
    return None, None, "OPEN"


def run_gfs_backtest(
    ohlcv: pd.DataFrame,
    config: GFSBacktestConfig = DEFAULT_GFS_BACKTEST_CONFIG,
    from_date: dt.datetime | None = None,
    to_date: dt.datetime | None = None,
) -> SystemOneBacktestResult:
    """`ohlcv`: DAILY candles, DatetimeIndex ascending, with open/high/low/close.
    Candles before `from_date` only warm up the indicators (monthly RSI needs
    years of history); a signal is accepted only on/after `from_date`.
    One trade at a time: a signal while a trade is open is ignored."""
    result = SystemOneBacktestResult()
    if ohlcv is None or ohlcv.empty or "close" not in ohlcv.columns:
        result.warnings.append("No candle data available.")
        return result

    df = ohlcv.sort_index()
    if to_date is not None:
        df = df.loc[df.index <= to_date]
    result.candles_used = len(df)
    min_candles = config.rsi_period + 2
    if len(df) < min_candles:
        result.warnings.append(f"Insufficient history: need at least {min_candles} candles, found {len(df)}.")
        return result

    dates = list(df.index)
    closes = df["close"].astype(float).tolist()
    _, weekly_rsi, _ = _rsi_series(df, config)
    signals, rsi_values = _gfs_setup_signals(df, config)
    n = len(df)
    risk_per_trade = config.risk_per_trade

    def _col(name: str) -> list[float]:
        return df[name].astype(float).tolist() if name in df.columns else closes

    opens, highs, lows = _col("open"), _col("high"), _col("low")
    result.series = [
        SeriesPoint(
            date=dates[k], open=opens[k], high=highs[k], low=lows[k], close=closes[k],
            rsi=None if rsi_values[k] != rsi_values[k] else rsi_values[k], ma=None,
        )
        for k in range(n)
        if from_date is None or dates[k] >= from_date
    ]

    i = 1
    while i < n:
        if (from_date is not None and dates[i] < from_date) or not signals[i]:
            i += 1
            continue
        entry_idx = i + 1
        if entry_idx >= n:
            result.skipped.append(SkippedSignal(dates[i], "No next candle yet to enter on (signal on the last candle)."))
            break

        entry_price = closes[entry_idx]
        stop = _initial_stop(lows, entry_idx, config.initial_stop_candles)
        if stop is None or entry_price <= stop:
            result.skipped.append(SkippedSignal(
                dates[i],
                "Not enough candles for the stop." if stop is None else
                f"Entry price {entry_price:.2f} is not above the stop {stop:.2f} "
                f"(lowest low of the last {config.initial_stop_candles} candles); risk per share would be zero or negative.",
            ))
            i += 1
            continue
        risk_per_share = entry_price - stop
        quantity = math.floor(risk_per_trade / risk_per_share + _FLOOR_EPSILON)
        if quantity < 1:
            result.skipped.append(SkippedSignal(
                dates[i],
                f"Quantity would be 0: risk per share {risk_per_share:.2f} is above the risk per trade {risk_per_trade:.2f}.",
            ))
            i += 1
            continue

        trade = SystemOneTrade(
            trade_number=len(result.trades) + 1, signal_date=dates[i], entry_date=dates[entry_idx],
            entry_price=entry_price, stop_loss=stop, risk_per_share=risk_per_share,
            risk_per_trade=risk_per_trade, quantity=quantity, status="OPEN",
        )
        exit_idx, exit_price, reason = _manage_trade(
            opens, lows, closes, weekly_rsi, entry_idx, entry_price, stop, config
        )
        if exit_idx is not None:
            trade.status = "CLOSED"
            trade.exit_date, trade.exit_price, trade.exit_reason = dates[exit_idx], exit_price, reason
            trade.holding_periods = exit_idx - entry_idx
            trade.data_flag = {
                "STOP_HIT": "Low-vs-High order inside the candle is unknown; a touched stop is assumed hit",
                "GAP_OPEN_BELOW_STOP": "Gap fill at the candle's open",
                "WEEKLY_RSI_EXIT": "Closed at the candle's close because the completed weekly RSI fell below the minimum",
            }[reason]
            trade.pnl_amount = (exit_price - entry_price) * quantity
            trade.pnl_pct = (exit_price - entry_price) / entry_price * 100.0
            trade.r_multiple = trade.pnl_amount / risk_per_trade
        else:
            trade.holding_periods = n - 1 - entry_idx
            trade.unrealized_pnl = (closes[n - 1] - entry_price) * quantity
        result.trades.append(trade)
        # Closed: look for the next signal after the exit candle. Open: nothing left to scan.
        i = exit_idx + 1 if exit_idx is not None else n

    result.weekly_series = _bars_with_rsi(to_weekly(df), config.rsi_period, from_date)
    result.monthly_series = _bars_with_rsi(to_monthly(df), config.rsi_period, from_date)
    return result


def run_advanced_gfs_backtest(
    ohlcv: pd.DataFrame,
    config: AdvancedGFSBacktestConfig = DEFAULT_ADVANCED_GFS_BACKTEST_CONFIG,
    from_date: dt.datetime | None = None,
    to_date: dt.datetime | None = None,
) -> SystemOneBacktestResult:
    """Advanced GFS: monthly, weekly and daily RSI must all be above 60; entry on
    the next candle close, same staged stop as GFS."""
    return run_gfs_backtest(ohlcv, config, from_date, to_date)


def run_gfs50_backtest(
    ohlcv: pd.DataFrame,
    config: Gfs50BacktestConfig = DEFAULT_GFS50_BACKTEST_CONFIG,
    from_date: dt.datetime | None = None,
    to_date: dt.datetime | None = None,
) -> SystemOneBacktestResult:
    """50 GFS: monthly and weekly RSI above 60 and daily RSI inside 50-59 (inclusive); a
    signal is the first candle inside the band, entry on the next candle close, same
    staged stop as GFS."""
    return run_gfs_backtest(ohlcv, config, from_date, to_date)
