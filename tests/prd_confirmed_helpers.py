"""Shared fixtures for the NEW PRD_CONFIRMED definition (reference RSI bottom
vs the latest completed candle). RSI is stubbed so each test controls the
exact values; nothing here touches the real RSI calculation."""
import pandas as pd
import pytest

from backend.strategies import prd as prd_mod

A_LOW_MARK = 90.0  # the frame's low on the reference-price-low candle


def confirmed_frame(n: int = 30, a_from_end: int = 6, b_close: float = 105.0, a_low: float = A_LOW_MARK) -> pd.DataFrame:
    """Flat candles; ONE candle `a_from_end` bars before the last has the
    reference price low (`a_low`). The last candle closes at `b_close`."""
    idx = pd.bdate_range("2024-01-01", periods=n)
    low = [100.0] * n
    low[n - 1 - a_from_end] = a_low
    close = [102.0] * n
    close[-1] = b_close
    return pd.DataFrame(
        {"open": [101.0] * n, "high": [110.0] * n, "low": low, "close": close, "volume": [1000] * n}, index=idx
    )


def install_rsi(monkeypatch, a_rsi: float = 70.0, b_rsi: float = 65.0, other: float = 80.0, a_from_end: int = 6):
    """RSI = `other` everywhere, a dip to `a_rsi` (a real 1-bar RSI low) on the
    reference candle, `b_rsi` on the last candle. Applies to every timeframe
    resampled from the same frame by counting back from the end."""

    def _rsi(close, period=14):
        vals = pd.Series(other, index=close.index)
        n = len(close)
        if n > a_from_end + 1:
            vals.iloc[n - 1 - a_from_end] = a_rsi
        vals.iloc[-1] = b_rsi
        return vals

    monkeypatch.setattr(prd_mod, "rsi", _rsi)


@pytest.fixture
def confirmed_rsi(monkeypatch):
    install_rsi(monkeypatch)
