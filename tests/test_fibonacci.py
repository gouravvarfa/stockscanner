import pandas as pd

from backend.config.strategy_config import FibonacciConfig
from backend.fibonacci.engine import calculate_fibonacci


def _series(values):
    return pd.Series(values, index=pd.date_range("2024-01-01", periods=len(values), freq="D"), dtype=float)


def test_uptrend_retracement_levels_between_high_and_low():
    # Rally from 100 to 200, then pull back to 161.8 (the 38.2% retracement level).
    close = _series([100] + [200] * 5 + [161.8])
    high = close.copy()
    low = close.copy()

    config = FibonacciConfig()
    analysis = calculate_fibonacci(high, low, close, config)

    assert analysis is not None
    assert analysis.direction == "uptrend_retracement"
    assert analysis.swing_low == 100
    assert analysis.swing_high == 200

    level_382 = next(lvl for lvl in analysis.levels if lvl.ratio == 0.382)
    assert level_382.price == 200 - (200 - 100) * 0.382
    assert abs(level_382.distance_pct) < 1.0  # current price sits right on this level


def test_nearest_level_is_closest_by_distance():
    close = _series([100] + [200] * 5 + [138.2])  # near the 61.8% retracement
    high = close.copy()
    low = close.copy()
    config = FibonacciConfig()

    analysis = calculate_fibonacci(high, low, close, config)
    assert analysis.nearest_level.ratio == 0.618


def test_downtrend_retracement_direction():
    close = _series([200] + [100] * 5 + [138.2])  # fall then bounce
    high = close.copy()
    low = close.copy()
    config = FibonacciConfig()

    analysis = calculate_fibonacci(high, low, close, config)
    assert analysis.direction == "downtrend_retracement"


def test_returns_none_for_degenerate_series():
    close = _series([100.0])
    high = close.copy()
    low = close.copy()
    config = FibonacciConfig()

    assert calculate_fibonacci(high, low, close, config) is None
