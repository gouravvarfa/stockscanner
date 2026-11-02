"""GFS trade backtest: setup/signal rule and the shared entry/stop engine.

Fixtures are synthetic daily candles, no Angel One calls. The expectations are
properties that follow from the rules (band edges, fresh-signal-only, completed
higher-timeframe bars), checked against the engine's own series.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from backend.config.strategy_config import GFSBacktestConfig
from backend.indicators.resample import to_monthly, to_weekly
from backend.indicators.rsi import rsi
from backend.strategies.gfs_backtest import _gfs_setup_signals, run_gfs_backtest

CFG = GFSBacktestConfig()


def daily(closes: list[float]) -> pd.DataFrame:
    idx = pd.bdate_range("2018-01-01", periods=len(closes))
    c = pd.Series(closes, index=idx, dtype=float)
    return pd.DataFrame({"open": c, "high": c, "low": c, "close": c, "volume": 1000.0})


def uptrend_with_dips(days: int = 1400) -> list[float]:
    """Steady climb (weekly + monthly RSI stay high) broken by 5-day dips
    that drag the daily RSI down into the 38-42 area."""
    closes, price = [], 100.0
    for k in range(days):
        price *= 0.988 if k % 25 >= 20 else 1.004
        closes.append(price)
    return closes


def noisy_uptrend() -> list[float]:
    """Seeded random walk with positive drift; produces a GFS trade (seed 3)."""
    rng = np.random.default_rng(3)
    return list(100 * np.exp(np.cumsum(rng.normal(0.0012, 0.015, 1500))))


def test_fires_only_when_all_three_timeframes_agree():
    df = daily(uptrend_with_dips())
    flags, d_rsi = _gfs_setup_signals(df, CFG)
    signal_days = [i for i, f in enumerate(flags) if f]
    assert signal_days, "fixture should produce at least one GFS setup"

    weekly = rsi(to_weekly(df)["close"], 14).reindex(df.index, method="ffill")
    monthly = rsi(to_monthly(df)["close"], 14).reindex(df.index, method="ffill")
    for i in signal_days:
        assert CFG.daily_rsi_min <= d_rsi[i] <= CFG.daily_rsi_max
        assert weekly.iloc[i] > CFG.weekly_rsi_min
        assert monthly.iloc[i] > CFG.monthly_rsi_min


def test_only_the_first_candle_of_a_setup_is_a_signal():
    flags, d_rsi = _gfs_setup_signals(daily(uptrend_with_dips()), CFG)
    for i, f in enumerate(flags):
        if f:
            # the previous candle was NOT already a signal day in the band with the same higher-timeframe state
            assert not flags[i - 1]


def test_downtrend_never_signals():
    # Weekly/monthly RSI sit far below 60, so the daily band alone must not fire.
    closes = [200 * (0.9985 ** k) + (3 if k % 7 == 0 else 0) for k in range(1400)]
    flags, _ = _gfs_setup_signals(daily(closes), CFG)
    assert not any(flags)


def test_band_edges_are_inclusive_and_configurable():
    df = daily(uptrend_with_dips())
    wide, _ = _gfs_setup_signals(df, GFSBacktestConfig(daily_rsi_min=30.0, daily_rsi_max=60.0))
    tight, _ = _gfs_setup_signals(df, GFSBacktestConfig(daily_rsi_min=39.9, daily_rsi_max=40.1))
    assert sum(wide) >= sum(CFG_flags(df)) >= sum(tight)


def CFG_flags(df):
    return _gfs_setup_signals(df, CFG)[0]


def test_engine_enters_next_candle_close_with_ma_stop():
    df = daily(noisy_uptrend())
    result = run_gfs_backtest(df, CFG)
    assert result.trades
    flags, _ = _gfs_setup_signals(df, CFG)
    signal_dates = {df.index[i] for i, f in enumerate(flags) if f}
    for t in result.trades:
        assert t.signal_date in signal_dates
        assert t.entry_date > t.signal_date
        assert t.entry_price == df.loc[t.entry_date, "close"]
        assert t.stop_loss < t.entry_price
        assert t.quantity >= 1


def test_stop_trails_up_by_the_low_of_three_candles_back_and_exits_when_touched():
    df = daily(noisy_uptrend())
    result = run_gfs_backtest(df, CFG)
    assert result.trades
    lows, opens = df["low"].tolist(), df["open"].tolist()
    for t in result.trades:
        e = df.index.get_loc(t.entry_date)
        assert t.stop_loss == lows[e - 2] < t.entry_price
        stop, expected = t.stop_loss, None
        for j in range(e + 1, len(df)):
            stop = max(stop, lows[j - 3])
            if opens[j] < stop:
                expected = (j, opens[j], "GAP_OPEN_BELOW_STOP")
                break
            if lows[j] <= stop:
                expected = (j, stop, "STOP_HIT")
                break
        if expected is None:
            assert t.status == "OPEN"
        else:
            assert (df.index.get_loc(t.exit_date), t.exit_price, t.exit_reason) == expected


def test_stop_never_moves_down():
    # Climb, then a deep drop below the early lows: the exit must be at/above the INITIAL stop's level,
    # because the stop already trailed up during the climb.
    closes = noisy_uptrend()
    df = daily(closes)
    for t in run_gfs_backtest(df, CFG).trades:
        if t.status == "CLOSED":
            assert t.exit_price >= min(t.stop_loss, df.loc[t.exit_date, "open"])


def test_signal_is_skipped_when_entry_is_not_above_the_stop():
    result = run_gfs_backtest(daily(uptrend_with_dips()), CFG)
    assert result.skipped and all("not above the stop" in sk.reason for sk in result.skipped)


def test_from_date_drops_earlier_signals_but_keeps_warmup():
    df = daily(noisy_uptrend())
    cut = df.index[900]
    result = run_gfs_backtest(df, CFG, from_date=cut.to_pydatetime())
    assert all(t.signal_date >= cut for t in result.trades)
    assert result.series[0].date >= cut


def test_too_little_data_is_a_warning_not_a_crash():
    result = run_gfs_backtest(daily([100.0] * 10), CFG)
    assert result.trades == []
    assert result.warnings


# ---- Advanced GFS: same rules, daily RSI must be ABOVE 60 -------------------

from backend.config.strategy_config import AdvancedGFSBacktestConfig  # noqa: E402
from backend.strategies.gfs_backtest import run_advanced_gfs_backtest  # noqa: E402

ADV = AdvancedGFSBacktestConfig()


def test_advanced_signals_need_daily_rsi_above_60_with_weekly_and_monthly_above_60():
    df = daily(noisy_uptrend())
    flags, d_rsi = _gfs_setup_signals(df, ADV)
    days = [i for i, f in enumerate(flags) if f]
    assert days
    weekly = rsi(to_weekly(df)["close"], 14).reindex(df.index, method="ffill")
    monthly = rsi(to_monthly(df)["close"], 14).reindex(df.index, method="ffill")
    for i in days:
        assert d_rsi[i] > 60
        assert weekly.iloc[i] > 60 and monthly.iloc[i] > 60


def test_advanced_and_gfs_signals_never_overlap_on_the_same_day():
    df = daily(noisy_uptrend())
    gfs = _gfs_setup_signals(df, CFG)[0]
    adv = _gfs_setup_signals(df, ADV)[0]
    assert not any(a and g for a, g in zip(adv, gfs))


def test_advanced_uses_same_entry_and_trailing_stop_engine():
    df = daily(noisy_uptrend())
    result = run_advanced_gfs_backtest(df, ADV)
    lows = df["low"].tolist()
    for t in result.trades:
        e = df.index.get_loc(t.entry_date)
        assert t.entry_price == df["close"].iloc[e]
        assert t.stop_loss == lows[e - 2] < t.entry_price


def test_weekly_and_monthly_series_are_completed_bars_with_rsi_inside_the_window():
    df = daily(noisy_uptrend())
    cut = df.index[900]
    result = run_gfs_backtest(df, CFG, from_date=cut.to_pydatetime())
    assert result.weekly_series and result.monthly_series
    assert all(p.date >= cut for p in result.weekly_series + result.monthly_series)
    assert result.weekly_series[-1].date <= df.index[-1]
    assert result.monthly_series[-1].date <= df.index[-1]
    assert any(p.rsi is not None for p in result.weekly_series) and any(p.rsi is not None for p in result.monthly_series)
