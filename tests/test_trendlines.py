import pandas as pd

from backend.trendlines.engine import detect_key_reversal, detect_trendline_breakout


def _series(values):
    idx = pd.date_range("2024-01-01", periods=len(values), freq="D")
    return pd.DataFrame(
        {
            "open": values,
            "high": [v + 1 for v in values],
            "low": [v - 1 for v in values],
            "close": values,
            "volume": [1000] * len(values),
        },
        index=idx,
    )


def _descending_trendline_then_breakout_prices():
    peak1_up = [100 + 5 * i for i in range(1, 11)]    # -> 150 (swing high)
    peak1_down = [150 - 4 * i for i in range(1, 11)]  # -> 110
    peak2_up = [110 + 3 * i for i in range(1, 11)]    # -> 140 (lower high -> descending line)
    peak2_down = [140 - 4 * i for i in range(1, 6)]   # -> 120
    breakout_up = [120 + 8 * i for i in range(1, 8)]  # strong rally through the trendline
    return peak1_up + peak1_down + peak2_up + peak2_down + breakout_up


def test_trendline_breakout_detected_on_real_descending_swing_highs():
    df = _series(_descending_trendline_then_breakout_prices())
    result = detect_trendline_breakout(df, swing_lookback=3)
    assert result.detected
    assert result.anchor1.price > result.anchor2.price  # confirms it's a descending line
    assert result.breakout_price > result.trendline_price_at_breakout


def test_no_breakout_when_price_stays_under_trendline():
    prices = _descending_trendline_then_breakout_prices()[:-7]  # drop the breakout rally
    df = _series(prices + [118, 117, 116])  # stays flat, well under the line
    result = detect_trendline_breakout(df, swing_lookback=3)
    assert not result.detected


def test_rising_swing_highs_are_not_treated_as_resistance():
    # Swing highs getting HIGHER isn't a descending trendline to break through.
    prices = [100 + i for i in range(60)]
    df = _series(prices)
    result = detect_trendline_breakout(df, swing_lookback=3)
    assert not result.detected


def test_key_reversal_detected_on_new_low_then_bullish_close():
    df = pd.DataFrame(
        {
            "open": [100, 105, 110, 108, 95, 100],
            "high": [101, 106, 111, 109, 96, 113],
            "low": [99, 104, 109, 90, 92, 85],
            "close": [100, 105, 110, 91, 82, 112],
            "volume": [1000] * 6,
        },
        index=pd.date_range("2024-01-01", periods=6, freq="D"),
    )
    result = detect_key_reversal(df)
    assert result.detected


def test_no_key_reversal_on_plain_uptrend():
    df = _series([100 + i for i in range(10)])
    result = detect_key_reversal(df)
    assert not result.detected
