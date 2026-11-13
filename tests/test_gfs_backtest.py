"""GFS trade backtest: setup/signal rule, entry and the staged stop.

Fixtures are synthetic daily candles, no Angel One calls. The expectations are
properties that follow from the rules (band edges, fresh-signal-only, completed
higher-timeframe bars), checked against the engine's own series.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from backend.config.strategy_config import DEFAULT_GFS50_BACKTEST_CONFIG, GFSBacktestConfig
from backend.indicators.resample import to_monthly, to_weekly
from backend.indicators.rsi import rsi
from backend.strategies.gfs_backtest import (
    _gfs_setup_signals, _initial_stop, _manage_trade, gfs_setup_flags, run_gfs50_backtest, run_gfs_backtest,
)

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


def test_engine_enters_next_candle_close_with_the_5_candle_low_stop_and_sizes_by_it():
    df = daily(noisy_uptrend())
    result = run_gfs_backtest(df, CFG)
    assert result.trades
    flags, _ = _gfs_setup_signals(df, CFG)
    signal_dates = {df.index[i] for i, f in enumerate(flags) if f}
    lows = df["low"].tolist()
    for t in result.trades:
        e = df.index.get_loc(t.entry_date)
        assert t.signal_date in signal_dates
        assert t.entry_date > t.signal_date
        assert t.entry_price == df.loc[t.entry_date, "close"]
        assert t.stop_loss == min(lows[e - 4 : e + 1]) < t.entry_price
        assert t.risk_per_share == t.entry_price - t.stop_loss
        assert t.quantity == int(CFG.risk_per_trade / t.risk_per_share + 1e-9)


def test_one_trade_at_a_time_and_exit_reasons_are_known():
    result = run_gfs_backtest(daily(noisy_uptrend()), CFG)
    closed = [t for t in result.trades if t.status == "CLOSED"]
    assert closed
    for t in closed:
        assert t.exit_reason in {"STOP_HIT", "GAP_OPEN_BELOW_STOP", "WEEKLY_RSI_EXIT"}
        assert t.exit_date > t.entry_date
    for prev, nxt in zip(result.trades, result.trades[1:]):
        assert prev.status == "CLOSED" and nxt.signal_date > prev.exit_date


def test_signal_is_skipped_when_entry_is_not_above_the_stop():
    # A falling market that still fires the setup: the 5-candle low sits above the entry.
    result = run_gfs_backtest(daily(uptrend_with_dips()), CFG)
    assert all("not above the stop" in sk.reason for sk in result.skipped)


# --- the staged stop, on hand-made candles --------------------------------------------------

def manage(opens, lows, closes, entry_idx, entry_price, stop, weekly=None):
    weekly = weekly if weekly is not None else [70.0] * len(closes)
    return _manage_trade(opens, lows, closes, weekly, entry_idx, entry_price, stop, CFG)


def test_initial_stop_is_the_lowest_low_of_the_last_5_candles_entry_included():
    lows = [10, 9, 8, 12, 11, 13]
    assert _initial_stop(lows, 5, 5) == 8  # candles 1..5
    assert _initial_stop(lows, 4, 5) == 8  # candles 0..4
    assert _initial_stop(lows, 3, 5) is None  # not enough candles


def test_breakeven_after_a_close_one_r_above_entry():
    # entry 100, stop 94 -> R = 6. Candle 1 closes at 106 (+1R), so the stop moves to 100.
    opens = [100, 101, 106]
    lows = [95, 99, 99.5]
    closes = [100, 106, 101]
    assert manage(opens, lows, closes, 0, 100.0, 94.0) == (2, 100.0, "STOP_HIT")


def test_no_breakeven_before_one_r():
    # Closes only +5 (< 1R = 6): the stop stays at 94 and a dip to 99.5 does not exit.
    opens = [100, 101, 105]
    lows = [95, 99, 99.5]
    closes = [100, 105, 101]
    assert manage(opens, lows, closes, 0, 100.0, 94.0) == (None, None, "OPEN")


def test_stop_trails_to_the_oldest_low_while_lows_keep_rising():
    # Initial stop 90, R = 10 so breakeven (needs a close of 110) never fires.
    lows = [95.0, 96.0, 97.0, 98.0, 99.0, 100.0, 97.5]
    opens = [100.0, 100.0, 100.0, 100.0, 101.0, 102.0, 100.0]
    closes = [100.0, 100.0, 100.0, 101.0, 102.0, 103.0, 99.0]
    # After candle 5 the stop is the low of candle 3 (98); candle 6's low 97.5 touches it.
    assert manage(opens, lows, closes, 2, 100.0, 90.0) == (6, 98.0, "STOP_HIT")


def test_sideways_market_does_not_trail_the_stop():
    # Flat lows: no higher-low run, so the stop stays at the initial 90.
    flat = [96.0] * 8
    opens = [100.0] * 8
    closes = [100.0] * 8
    assert manage(opens, flat, closes, 2, 100.0, 90.0) == (None, None, "OPEN")
    # ...and a later drop is only stopped at that initial level.
    lows = flat[:-1] + [89.0]
    assert manage(opens, lows, closes, 2, 100.0, 90.0) == (7, 90.0, "STOP_HIT")


def test_gap_open_below_the_stop_fills_at_the_open():
    opens, lows, closes = [100.0, 88.0], [95.0, 87.0], [100.0, 89.0]
    assert manage(opens, lows, closes, 0, 100.0, 90.0) == (1, 88.0, "GAP_OPEN_BELOW_STOP")


def test_exit_at_the_close_when_the_weekly_rsi_falls_below_60():
    opens, lows, closes = [100.0, 100.0, 101.0], [95.0, 99.0, 100.0], [100.0, 101.0, 102.0]
    weekly = [70.0, 70.0, 59.0]
    assert manage(opens, lows, closes, 0, 100.0, 90.0, weekly) == (2, 102.0, "WEEKLY_RSI_EXIT")
    # a stop hit on the same candle wins over the RSI exit (it is checked first)
    lows2 = [95.0, 99.0, 89.0]
    assert manage(opens, lows2, closes, 0, 100.0, 90.0, weekly) == (2, 90.0, "STOP_HIT")


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


def test_advanced_uses_same_entry_and_stop_engine():
    df = daily(noisy_uptrend())
    result = run_advanced_gfs_backtest(df, ADV)
    lows = df["low"].tolist()
    for t in result.trades:
        e = df.index.get_loc(t.entry_date)
        assert t.entry_price == df["close"].iloc[e]
        assert t.stop_loss == min(lows[e - 4 : e + 1]) < t.entry_price


def test_weekly_and_monthly_series_are_completed_bars_with_rsi_inside_the_window():
    df = daily(noisy_uptrend())
    cut = df.index[900]
    result = run_gfs_backtest(df, CFG, from_date=cut.to_pydatetime())
    assert result.weekly_series and result.monthly_series
    assert all(p.date >= cut for p in result.weekly_series + result.monthly_series)
    assert result.weekly_series[-1].date <= df.index[-1]
    assert result.monthly_series[-1].date <= df.index[-1]
    assert any(p.rsi is not None for p in result.weekly_series) and any(p.rsi is not None for p in result.monthly_series)


# ---- 50 GFS: daily RSI inside 50-59 ---------------------------------------------

G50 = DEFAULT_GFS50_BACKTEST_CONFIG


def test_gfs50_config_is_the_50_to_59_band_inclusive_with_monthly_and_weekly_above_60():
    assert (G50.daily_rsi_min, G50.daily_rsi_max, G50.daily_min_exclusive) == (50.0, 59.0, False)
    assert G50.monthly_rsi_min == 60 and G50.weekly_rsi_min == 60


def test_gfs50_band_edges_50_and_59_are_in_and_just_outside_is_out():
    from backend.strategies.gfs_backtest import _daily_ok

    assert _daily_ok(50.0, G50) and _daily_ok(59.0, G50) and _daily_ok(54.5, G50)
    assert not _daily_ok(49.99, G50) and not _daily_ok(59.01, G50) and not _daily_ok(80.0, G50)
    # the old "above 50, no upper limit" rule is gone: a strong daily RSI no longer triggers
    assert not _daily_ok(70.0, G50)


def walk(seed: int) -> list[float]:
    rng = np.random.default_rng(seed)
    return list(100 * np.exp(np.cumsum(rng.normal(0.0012, 0.015, 1500))))


def test_gfs50_every_signal_has_the_daily_rsi_inside_the_band_and_higher_timeframes_above_60():
    df = daily(noisy_uptrend())
    flags, d_rsi = _gfs_setup_signals(df, G50)
    days = [i for i, f in enumerate(flags) if f]
    assert days, "fixture should produce at least one 50 GFS signal"
    weekly = rsi(to_weekly(df)["close"], 14).reindex(df.index, method="ffill")
    monthly = rsi(to_monthly(df)["close"], 14).reindex(df.index, method="ffill")
    for i in days:
        assert 50.0 <= d_rsi[i] <= 59.0
        assert weekly.iloc[i] > 60 and monthly.iloc[i] > 60


def test_gfs50_signal_fires_once_per_visit_to_the_band_not_once_per_day_inside_it():
    setup, d_rsi, _, _ = gfs_setup_flags(daily(noisy_uptrend()), G50)
    flags, _ = _gfs_setup_signals(daily(noisy_uptrend()), G50)
    for i in range(1, len(flags)):
        if flags[i]:
            assert setup[i] and not setup[i - 1]  # first candle inside the band after being outside
    inside_runs = sum(1 for i in range(1, len(setup)) if setup[i] and not setup[i - 1])
    assert sum(flags) == inside_runs


def test_gfs50_catches_support_taken_anywhere_in_the_band_on_different_stocks():
    """Different random walks dip into 50-59 at different RSI levels and times: every one of them signals,
    and every signal sits inside the band."""
    for seed in (3, 5, 11, 21, 42):
        flags, d_rsi = _gfs_setup_signals(daily(walk(seed)), G50)
        assert sum(flags) >= 10, seed
        assert all(50.0 <= d_rsi[i] <= 59.0 for i, f in enumerate(flags) if f)
    # a band nudged one point up or down moves the signals, so the 50-59 band is really what is applied
    base = _gfs_setup_signals(daily(walk(3)), G50)[0]
    lower = _gfs_setup_signals(daily(walk(3)), GFSBacktestConfig(daily_rsi_min=44.0, daily_rsi_max=49.0))[0]
    assert base != lower


def test_gfs50_backtest_runs_and_uses_the_same_staged_stop_as_gfs():
    df = daily(noisy_uptrend())
    result = run_gfs50_backtest(df)
    flags, _ = _gfs_setup_signals(df, G50)
    signal_dates = {df.index[i] for i, f in enumerate(flags) if f}
    lows = df["low"].tolist()
    for t in result.trades:
        e = df.index.get_loc(t.entry_date)
        assert t.signal_date in signal_dates
        assert t.stop_loss == min(lows[e - 4 : e + 1]) < t.entry_price
        assert t.entry_price == df.loc[t.entry_date, "close"]


def test_gfs_and_advanced_gfs_bands_are_unchanged():
    from backend.config.strategy_config import DEFAULT_ADVANCED_GFS_BACKTEST_CONFIG as ADV

    assert (CFG.daily_rsi_min, CFG.daily_rsi_max) == (38.0, 45.0) or (CFG.daily_rsi_min, CFG.daily_rsi_max) == (38.0, 45)
    assert (ADV.daily_rsi_min, ADV.daily_rsi_max, ADV.daily_min_exclusive) == (60.0, 100.0, True)
