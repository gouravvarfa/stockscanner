"""
GFS trade backtest (daily candles).

Separate from the GFS *screener* in gfs.py (which uses its own 38-45 band) —
this one simulates the actual trades. Pure logic only: no network, no I/O.

Rules:
  * Setup  : on a daily candle ALL of these hold -
               monthly RSI(14) > 60, weekly RSI(14) > 60, daily RSI(14) in [38, 42].
  * Signal : the first candle where the setup holds after it did not hold on the
             previous candle (so a stock sitting in the zone gives one signal,
             not one per day).
  * Entry  : the CLOSE of the candle after the signal. No 20 MA condition.
  * Stop   : starts at the low of the first (oldest) of the last 3 candles ending
             on the entry candle (skipped if the entry is not above it). It then
             TRAILS UP: on every later candle it is the low of the candle 3 back
             (the first of the 3 candles ending on the previous candle) and never
             moves down. Position size uses the initial stop.
  * Exit   : the moment a candle opens below the stop (fill at its open) or its
             low touches the CURRENT stop (fill at the stop). One trade at a time; quantity =
             floor(risk per trade / (entry - stop)).

Weekly/monthly RSI use COMPLETED bars only: on a daily candle the value is that
of the latest weekly/monthly bar already closed, never the one still forming,
so a signal cannot lean on data from the future.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from backend.config.strategy_config import (
    DEFAULT_ADVANCED_GFS_BACKTEST_CONFIG,
    DEFAULT_GFS_BACKTEST_CONFIG,
    AdvancedGFSBacktestConfig,
    GFSBacktestConfig,
)
from backend.indicators.resample import to_monthly, to_weekly
from backend.indicators.rsi import rsi
from backend.strategies.system_one_backtest import SeriesPoint, SystemOneBacktestResult, run_ma_stop_backtest


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


def _gfs_setup_signals(df: pd.DataFrame, config: GFSBacktestConfig) -> "tuple[list[bool], list[float]]":
    daily_rsi = rsi(df["close"].astype(float), period=config.rsi_period).astype(float).tolist()
    weekly_rsi = _completed_rsi_on_daily_index(df, to_weekly(df), config.rsi_period)
    monthly_rsi = _completed_rsi_on_daily_index(df, to_monthly(df), config.rsi_period)

    setup = [
        _ok(m, lambda v: v > config.monthly_rsi_min)
        and _ok(w, lambda v: v > config.weekly_rsi_min)
        and _ok(d, lambda v: _daily_ok(v, config))
        for d, w, m in zip(daily_rsi, weekly_rsi, monthly_rsi)
    ]
    flags = [False] + [setup[k] and not setup[k - 1] for k in range(1, len(setup))]
    return flags, daily_rsi


def run_gfs_backtest(
    ohlcv: pd.DataFrame,
    config: GFSBacktestConfig = DEFAULT_GFS_BACKTEST_CONFIG,
    from_date: dt.datetime | None = None,
    to_date: dt.datetime | None = None,
) -> SystemOneBacktestResult:
    """`ohlcv`: DAILY candles, DatetimeIndex ascending, with open/high/low/close.
    Candles before `from_date` only warm up the indicators (monthly RSI needs
    years of history); a signal is accepted only on/after `from_date`."""
    result = run_ma_stop_backtest(
        ohlcv, config, _gfs_setup_signals, from_date, to_date, fixed_stop_candles=config.stop_candles
    )
    if result.series:
        df = ohlcv.sort_index()
        if to_date is not None:
            df = df.loc[df.index <= to_date]
        result.weekly_series = _bars_with_rsi(to_weekly(df), config.rsi_period, from_date)
        result.monthly_series = _bars_with_rsi(to_monthly(df), config.rsi_period, from_date)
    return result


def run_advanced_gfs_backtest(
    ohlcv: pd.DataFrame,
    config: AdvancedGFSBacktestConfig = DEFAULT_ADVANCED_GFS_BACKTEST_CONFIG,
    from_date: dt.datetime | None = None,
    to_date: dt.datetime | None = None,
) -> SystemOneBacktestResult:
    """Advanced GFS: same as GFS (monthly and weekly RSI > 60, entry on the next
    candle close, trailing 3-candle-low stop) but the daily RSI must be above 60."""
    return run_gfs_backtest(ohlcv, config, from_date, to_date)
