import pandas as pd

from backend.config.expiry_level_1_config import ExpiryLevel1Config
from backend.strategies.expiry_level_1 import detect_expiry_level_1_signal


def _series(values):
    idx = pd.date_range("2024-06-03 09:15", periods=len(values), freq="15min")
    return pd.Series(values, index=idx)


def test_1_59_to_61_with_1h_66_signals():
    rsi15 = _series([59.0, 61.0])
    rsi1h = _series([66.0])
    signal = detect_expiry_level_1_signal("NIFTY", "INDEX", "NIFTY", None, rsi15, rsi1h, ExpiryLevel1Config())
    assert signal is not None
    assert signal.status == "CONFIRMED"
    assert signal.cross_status == "FIRST_CROSS_ABOVE_60"
    assert signal.rsi_15m == 61.0
    assert signal.rsi_15m_prev == 59.0


def test_2_60_to_61_with_1h_66_signals():
    # Previous exactly at the threshold (<=60) still counts as "not yet crossed".
    rsi15 = _series([60.0, 61.0])
    rsi1h = _series([66.0])
    signal = detect_expiry_level_1_signal("NIFTY", "INDEX", "NIFTY", None, rsi15, rsi1h, ExpiryLevel1Config())
    assert signal is not None


def test_3_already_above_60_no_new_signal():
    # Previous confirmed candle was already above 60 — this is not a first cross.
    rsi15 = _series([62.0, 63.0])
    rsi1h = _series([66.0])
    signal = detect_expiry_level_1_signal("NIFTY", "INDEX", "NIFTY", None, rsi15, rsi1h, ExpiryLevel1Config())
    assert signal is None


def test_4_cross_but_1h_64_no_signal():
    rsi15 = _series([59.0, 61.0])
    rsi1h = _series([64.0])
    signal = detect_expiry_level_1_signal("NIFTY", "INDEX", "NIFTY", None, rsi15, rsi1h, ExpiryLevel1Config())
    assert signal is None


def test_5_cross_but_1h_exactly_65_no_signal():
    # Spec: 1H RSI must be strictly > 65.
    rsi15 = _series([59.0, 61.0])
    rsi1h = _series([65.0])
    signal = detect_expiry_level_1_signal("NIFTY", "INDEX", "NIFTY", None, rsi15, rsi1h, ExpiryLevel1Config())
    assert signal is None


def test_6_cross_with_1h_65_1_signals():
    rsi15 = _series([59.0, 61.0])
    rsi1h = _series([65.1])
    signal = detect_expiry_level_1_signal("NIFTY", "INDEX", "NIFTY", None, rsi15, rsi1h, ExpiryLevel1Config())
    assert signal is not None


def test_7_incomplete_15m_history_no_signal():
    # Fewer than two confirmed 15m candles — there is nothing to compare
    # against, so no cross can be confirmed yet.
    rsi15 = _series([61.0])
    rsi1h = _series([66.0])
    signal = detect_expiry_level_1_signal("NIFTY", "INDEX", "NIFTY", None, rsi15, rsi1h, ExpiryLevel1Config())
    assert signal is None


def test_7b_empty_series_no_signal():
    rsi15 = _series([])
    rsi1h = _series([])
    signal = detect_expiry_level_1_signal("NIFTY", "INDEX", "NIFTY", None, rsi15, rsi1h, ExpiryLevel1Config())
    assert signal is None


def test_8_reset_then_new_cross_signals_again():
    # 61 (first cross) -> 58 (reset, confirmed close back at/below 60) -> 62
    # (a brand new confirmed cross above 60). Only the latest two confirmed
    # candles matter, so evaluating at the final candle must signal again.
    rsi15 = _series([61.0, 58.0, 62.0])
    rsi1h = _series([66.0, 66.0, 66.0])
    signal = detect_expiry_level_1_signal("NIFTY", "INDEX", "NIFTY", None, rsi15, rsi1h, ExpiryLevel1Config())
    assert signal is not None
    assert signal.rsi_15m_prev == 58.0
    assert signal.rsi_15m == 62.0


def test_no_repeat_signal_while_rsi_stays_above_60():
    # Evaluating one candle further after the first cross (63.5, with the
    # previous confirmed candle already at 61.2, itself above 60) must not
    # re-signal — this is the "no repeat while still elevated" case from the
    # worked example in the spec.
    rsi15 = _series([59.4, 61.2, 63.5])
    rsi1h = _series([65.8, 66.1, 67.0])
    signal = detect_expiry_level_1_signal("NIFTY", "INDEX", "NIFTY", None, rsi15, rsi1h, ExpiryLevel1Config())
    assert signal is None


def test_stock_instrument_type_flows_through():
    rsi15 = _series([59.0, 61.0])
    rsi1h = _series([66.0])
    signal = detect_expiry_level_1_signal("RELIANCE", "STOCK", "Reliance Industries", "Energy", rsi15, rsi1h, ExpiryLevel1Config())
    assert signal is not None
    assert signal.instrument_type == "STOCK"
    assert signal.sector == "Energy"
