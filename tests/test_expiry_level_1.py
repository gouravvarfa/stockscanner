import pandas as pd

from backend.config.expiry_level_1_config import ExpiryLevel1Config
from backend.strategies.expiry_level_1 import detect_expiry_level_1_signal


def _series(values):
    idx = pd.date_range("2024-06-03 09:15", periods=len(values), freq="15min")
    return pd.Series(values, index=idx)


def test_15m_in_band_and_hourly_above_65_signals():
    rsi15 = _series([57.8, 59.4, 61.2])
    rsi1h = _series([64.2, 65.8, 66.1])
    signal = detect_expiry_level_1_signal("NIFTY", "INDEX", "NIFTY", None, rsi15, rsi1h, ExpiryLevel1Config())
    assert signal is not None
    assert signal.status == "CONFIRMED"


def test_15m_at_band_lower_edge_58_signals():
    rsi15 = _series([55.0, 56.0, 58.0])
    rsi1h = _series([64.0, 65.5, 66.0])
    signal = detect_expiry_level_1_signal("NIFTY", "INDEX", "NIFTY", None, rsi15, rsi1h, ExpiryLevel1Config())
    assert signal is not None


def test_15m_at_band_upper_edge_65_signals():
    rsi15 = _series([60.0, 62.0, 65.0])
    rsi1h = _series([64.0, 65.5, 66.0])
    signal = detect_expiry_level_1_signal("NIFTY", "INDEX", "NIFTY", None, rsi15, rsi1h, ExpiryLevel1Config())
    assert signal is not None


def test_15m_below_band_no_signal():
    rsi15 = _series([50.0, 55.0, 57.9])  # just under the 58 floor
    rsi1h = _series([66.0, 66.5, 67.0])
    signal = detect_expiry_level_1_signal("NIFTY", "INDEX", "NIFTY", None, rsi15, rsi1h, ExpiryLevel1Config())
    assert signal is None


def test_15m_above_band_no_signal():
    rsi15 = _series([60.0, 63.0, 65.1])  # just over the 65 ceiling
    rsi1h = _series([66.0, 66.5, 67.0])
    signal = detect_expiry_level_1_signal("NIFTY", "INDEX", "NIFTY", None, rsi15, rsi1h, ExpiryLevel1Config())
    assert signal is None


def test_15m_in_band_but_hourly_64_no_signal():
    rsi15 = _series([57.0, 59.0, 61.0])
    rsi1h = _series([63.0, 63.5, 64.0])
    signal = detect_expiry_level_1_signal("NIFTY", "INDEX", "NIFTY", None, rsi15, rsi1h, ExpiryLevel1Config())
    assert signal is None


def test_hourly_exactly_65_no_signal():
    # Spec: 1H RSI must be strictly > 65.
    rsi15 = _series([57.0, 59.0, 61.0])
    rsi1h = _series([64.0, 64.5, 65.0])
    signal = detect_expiry_level_1_signal("NIFTY", "INDEX", "NIFTY", None, rsi15, rsi1h, ExpiryLevel1Config())
    assert signal is None


def test_hourly_65_1_signals():
    rsi15 = _series([57.0, 59.0, 61.0])
    rsi1h = _series([64.0, 64.8, 65.1])
    signal = detect_expiry_level_1_signal("NIFTY", "INDEX", "NIFTY", None, rsi15, rsi1h, ExpiryLevel1Config())
    assert signal is not None


def test_single_confirmed_candle_is_enough_no_previous_needed():
    # The band check only needs the LATEST confirmed candle — unlike the old
    # "first cross" rule, there's no need for a previous value to compare
    # against, so even a single confirmed 15m candle is sufficient.
    rsi15 = _series([61.0])
    rsi1h = _series([66.0])
    signal = detect_expiry_level_1_signal("NIFTY", "INDEX", "NIFTY", None, rsi15, rsi1h, ExpiryLevel1Config())
    assert signal is not None


def test_no_data_no_signal():
    rsi15 = _series([])
    rsi1h = _series([])
    signal = detect_expiry_level_1_signal("NIFTY", "INDEX", "NIFTY", None, rsi15, rsi1h, ExpiryLevel1Config())
    assert signal is None


def test_signal_persists_while_still_in_band_not_a_one_time_cross():
    # Unlike the old "first confirmed cross" rule, the band condition is
    # evaluated fresh every scan — as long as 15m RSI stays in [58, 65] and
    # 1h RSI stays above 65, the signal keeps confirming on every candle.
    idx = pd.date_range("2024-06-03 09:15", periods=3, freq="15min")
    rsi15 = pd.Series([59.0, 61.0, 62.0], index=idx)
    rsi1h = pd.Series([66.0, 66.0, 66.0], index=idx)
    signal = detect_expiry_level_1_signal("NIFTY", "INDEX", "NIFTY", None, rsi15, rsi1h, ExpiryLevel1Config())
    assert signal is not None
