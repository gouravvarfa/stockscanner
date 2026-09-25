import pandas as pd

from backend.live.candle_builder import CandleBuilder, SymbolCandleSet, bucket_key


def test_15m_bucket_key_ceils_to_next_boundary():
    assert bucket_key("15m", pd.Timestamp("2026-09-25 09:16:00")) == pd.Timestamp("2026-09-25 09:30:00")
    assert bucket_key("15m", pd.Timestamp("2026-09-25 09:30:00")) == pd.Timestamp("2026-09-25 09:30:00")


def test_1h_bucket_key_ceils_to_next_hour():
    assert bucket_key("1H", pd.Timestamp("2026-09-25 10:05:00")) == pd.Timestamp("2026-09-25 11:00:00")


def test_1d_bucket_key_is_the_calendar_date():
    assert bucket_key("1D", pd.Timestamp("2026-09-25 14:22:00")) == pd.Timestamp("2026-09-25")


def test_first_tick_opens_a_new_candle():
    b = CandleBuilder("15m")
    c = b.on_tick(pd.Timestamp("2026-09-25 09:20:00"), 100.0)
    assert c.open == c.high == c.low == c.close == 100.0
    assert c.complete is False


def test_ticks_within_the_same_bucket_update_high_low_close_not_open():
    b = CandleBuilder("15m")
    b.on_tick(pd.Timestamp("2026-09-25 09:16:00"), 100.0)
    b.on_tick(pd.Timestamp("2026-09-25 09:20:00"), 105.0)
    c = b.on_tick(pd.Timestamp("2026-09-25 09:25:00"), 98.0)
    assert c.open == 100.0
    assert c.high == 105.0
    assert c.low == 98.0
    assert c.close == 98.0


def test_a_tick_in_the_next_bucket_finalizes_the_previous_candle():
    b = CandleBuilder("15m")
    b.on_tick(pd.Timestamp("2026-09-25 09:16:00"), 100.0)
    b.on_tick(pd.Timestamp("2026-09-25 09:29:00"), 105.0)
    b.on_tick(pd.Timestamp("2026-09-25 09:31:00"), 110.0)  # next 15m bucket
    assert len(b.history) == 1
    assert b.history[0].complete is True
    assert b.history[0].close == 105.0
    assert b.current.open == 110.0
    assert b.current.complete is False


def test_history_is_bounded_not_unlimited():
    b = CandleBuilder("15m", history_maxlen=3)
    t = pd.Timestamp("2026-09-25 09:16:00")
    for i in range(10):
        b.on_tick(t + pd.Timedelta(minutes=15 * i), 100.0 + i)
    assert len(b.history) == 3  # bounded, not 9


def test_cumulative_day_volume_is_converted_to_per_candle_delta():
    b = CandleBuilder("15m")
    b.on_tick(pd.Timestamp("2026-09-25 09:16:00"), 100.0, cumulative_day_volume=1000.0)
    c = b.on_tick(pd.Timestamp("2026-09-25 09:20:00"), 101.0, cumulative_day_volume=1500.0)
    assert c.volume == 1000.0 + 500.0  # first tick's own cumulative value + the delta since


def test_cumulative_day_volume_reset_at_new_trading_day_is_handled():
    b = CandleBuilder("1D")
    b.on_tick(pd.Timestamp("2026-09-24 15:29:00"), 100.0, cumulative_day_volume=50000.0)
    # Next day's cumulative counter restarts from a small number - must not go negative.
    c = b.on_tick(pd.Timestamp("2026-09-25 09:16:00"), 101.0, cumulative_day_volume=200.0)
    assert c.volume == 200.0


def test_finalize_if_period_ended_marks_current_candle_complete_without_a_new_tick():
    b = CandleBuilder("1D")
    b.on_tick(pd.Timestamp("2026-09-25 09:16:00"), 100.0)
    finalized = b.finalize_if_period_ended(pd.Timestamp("2026-09-25 15:30:00"))
    assert finalized is not None
    assert finalized.complete is True
    assert b.current.complete is True  # same object, still accessible as "current" until the next day's first tick


def test_finalize_if_period_ended_is_a_noop_when_nothing_to_finalize():
    b = CandleBuilder("1D")
    assert b.finalize_if_period_ended(pd.Timestamp("2026-09-25 15:30:00")) is None


def test_symbol_candle_set_builds_all_five_timeframes_from_one_tick():
    s = SymbolCandleSet(symbol="BHEL")
    candles = s.on_tick(pd.Timestamp("2026-09-25 10:00:00"), 250.0, cumulative_day_volume=1000.0)
    assert set(candles.keys()) == {"15m", "1H", "1D", "1W", "1M"}
    for c in candles.values():
        assert c.close == 250.0


def test_monthly_and_weekly_candles_match_the_historical_resample_labels():
    """The whole point of using the same bucket_key() as
    backend/indicators/resample.py's label="right" convention (see
    candle_builder.py's module docstring) - a live tick's monthly/weekly
    candle must have the EXACT same identity a historical resample would
    give that same calendar period, so chart series can switch from
    historical to live with no duplicate and no gap."""
    from backend.indicators.resample import to_monthly, to_weekly

    df = pd.DataFrame(
        {"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [1.0]},
        index=[pd.Timestamp("2026-09-10")],
    )
    monthly_label = to_monthly(df, include_partial=True).index[0]
    weekly_label = to_weekly(df, include_partial=True).index[0]
    assert bucket_key("1M", pd.Timestamp("2026-09-10")) == monthly_label
    assert bucket_key("1W", pd.Timestamp("2026-09-10")) == weekly_label
