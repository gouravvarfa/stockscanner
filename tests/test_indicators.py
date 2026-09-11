import numpy as np
import pandas as pd
import pytest

from backend.indicators.adx import adx
from backend.indicators.macd import macd
from backend.indicators.moving_averages import ema, sma
from backend.indicators.rsi import rsi
from backend.indicators.volume import distance_from_52w_high, volume_ratio


def _dates(n):
    return pd.date_range("2024-01-01", periods=n, freq="D")


def test_rsi_all_gains_is_100():
    close = pd.Series(range(1, 30), index=_dates(29), dtype=float)
    result = rsi(close, period=14)
    assert result.iloc[-1] == pytest.approx(100.0)


def test_rsi_all_losses_is_0():
    close = pd.Series(range(30, 1, -1), index=_dates(29), dtype=float)
    result = rsi(close, period=14)
    assert result.iloc[-1] == pytest.approx(0.0, abs=1e-6)


def test_rsi_known_reference_value():
    # Classic Wilder RSI worked example (14-period), values from a known series.
    prices = [
        44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08,
        45.89, 46.03, 45.61, 46.28, 46.28,
    ]
    close = pd.Series(prices, index=_dates(len(prices)))
    result = rsi(close, period=14)
    assert result.iloc[-1] == pytest.approx(70.53, abs=0.5)


def test_sma_matches_manual_average():
    close = pd.Series([1, 2, 3, 4, 5], dtype=float)
    result = sma(close, period=3)
    assert result.iloc[2] == pytest.approx(2.0)
    assert result.iloc[4] == pytest.approx(4.0)


def test_ema_converges_toward_constant_series():
    close = pd.Series([10.0] * 50)
    result = ema(close, period=20)
    assert result.iloc[-1] == pytest.approx(10.0)


def test_macd_zero_for_flat_price():
    close = pd.Series([100.0] * 60)
    result = macd(close)
    assert result["macd"].iloc[-1] == pytest.approx(0.0)
    assert result["histogram"].iloc[-1] == pytest.approx(0.0)


def test_adx_high_for_strong_uptrend():
    n = 60
    close = pd.Series(np.linspace(100, 200, n))
    high = close + 1
    low = close - 1
    result = adx(high, low, close, period=14)
    assert result["adx"].iloc[-1] > 30


def test_volume_ratio_above_one_when_spiking():
    volume = pd.Series([100] * 20 + [500])
    result = volume_ratio(volume, period=20)
    assert result.iloc[-1] > 1.0


def test_distance_from_52w_high_is_negative_below_high():
    close = pd.Series([90.0] * 10)
    high = pd.Series([100.0] * 9 + [90.0])
    result = distance_from_52w_high(close, high)
    assert result.iloc[-1] < 0
