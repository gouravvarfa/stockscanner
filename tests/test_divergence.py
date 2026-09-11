import pandas as pd

from backend.config.strategy_config import DivergenceConfig
from backend.divergence.detector import detect_divergences
from backend.divergence.swing import find_swing_points
from backend.indicators.rsi import rsi


def _series(values):
    return pd.Series(values, index=pd.date_range("2024-01-01", periods=len(values), freq="D"), dtype=float)


def _bearish_divergence_prices():
    # Sharp uniform rally to a first peak (all up-days -> RSI saturates at 100),
    # a pullback, then a choppy (some down-days) grind to a HIGHER peak whose
    # recent 14-bar window contains real losses -> lower RSI despite the higher price.
    leg1_up = [100 + 5 * i for i in range(1, 21)]        # 20 bars, peak = 200
    leg1_down = [200 - 4 * i for i in range(1, 11)]      # 10 bars decline -> 160
    leg2_up = []
    price = leg1_down[-1]
    for i in range(30):
        price += 5 if i % 2 == 0 else -2                 # choppy net-upward, peak = 207
        leg2_up.append(price)
    leg2_down = [leg2_up[-1] - 4 * i for i in range(1, 11)]  # confirmation bars after 2nd peak
    return leg1_up + leg1_down + leg2_up + leg2_down


def test_swing_points_detects_two_highs():
    prices = _bearish_divergence_prices()
    close = _series(prices)
    swings = find_swing_points(close, close, lookback=3)
    highs = [p for p in swings if p.kind == "high"]
    assert len(highs) >= 2


def test_detects_bearish_divergence_on_higher_high_lower_rsi():
    prices = _bearish_divergence_prices()
    close = _series(prices)
    rsi_series = rsi(close, period=14)

    config = DivergenceConfig(
        swing_lookback=3,
        min_price_difference_pct=0.1,
        min_rsi_difference=0.1,
        confirmation_candles=2,
    )
    signals = detect_divergences(close, close, close, rsi_series, config)
    bearish = [s for s in signals if s.kind == "bearish"]

    assert len(bearish) >= 1
    sig = bearish[0]
    assert sig.second_point.price > sig.first_point.price
    assert sig.second_rsi < sig.first_rsi


def test_no_divergence_when_rsi_confirms_price():
    # A clean, uniform uptrend: higher highs with correspondingly higher RSI —
    # no divergence should be reported.
    prices = [100 + i for i in range(60)]
    close = _series(prices)
    rsi_series = rsi(close, period=14)

    config = DivergenceConfig(swing_lookback=3, confirmation_candles=2)
    signals = detect_divergences(close, close, close, rsi_series, config)
    assert not any(s.kind == "bearish" for s in signals)
