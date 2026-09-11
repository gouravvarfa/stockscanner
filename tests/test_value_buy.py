import pandas as pd

from backend.config.multi_strategy_config import ValueBuyConfig
from backend.strategies.value_buy import evaluate_value_buy
from tests.strategy_helpers import make_result


def _bseries(values, start="2024-01-01"):
    idx = pd.bdate_range(start, periods=len(values))
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


def _breakout_and_green_week_prices():
    peak1_up = [100 + 5 * i for i in range(1, 11)]
    peak1_down = [150 - 4 * i for i in range(1, 11)]
    peak2_up = [110 + 3 * i for i in range(1, 11)]
    peak2_down = [140 - 4 * i for i in range(1, 6)]
    breakout_up = [120 + 8 * i for i in range(1, 8)]
    return peak1_up + peak1_down + peak2_up + peak2_down + breakout_up


def test_value_buy_qualifies_when_all_three_conditions_hold():
    df = _bseries(_breakout_and_green_week_prices())
    result = make_result(monthly_rsi=40.0)  # inside default 35-45 support zone
    signal = evaluate_value_buy(result, df, ValueBuyConfig())
    assert signal.qualifies
    assert all(signal.conditions.values())


def test_value_buy_rejects_when_monthly_rsi_outside_support_zone():
    df = _bseries(_breakout_and_green_week_prices())
    result = make_result(monthly_rsi=70.0)  # not in support zone
    signal = evaluate_value_buy(result, df, ValueBuyConfig())
    assert not signal.qualifies
    assert not signal.conditions["monthly_rsi_in_support_zone"]


def test_value_buy_rejects_without_key_reversal_or_breakout():
    flat_prices = [100 + (i % 3) for i in range(60)]  # no breakout, no reversal
    df = _bseries(flat_prices)
    result = make_result(monthly_rsi=40.0)
    signal = evaluate_value_buy(result, df, ValueBuyConfig())
    assert not signal.qualifies
    assert not signal.conditions["key_reversal_or_trendline_breakout"]


def test_value_buy_rejects_when_latest_confirmed_week_is_red():
    # A clean, monotonically declining series (Mon-start, whole weeks) — the
    # latest CONFIRMED week must close red every time, regardless of any
    # other condition.
    df = _bseries([200 - i for i in range(15)], start="2024-01-01")
    result = make_result(monthly_rsi=40.0)
    signal = evaluate_value_buy(result, df, ValueBuyConfig())
    assert not signal.conditions["latest_confirmed_weekly_candle_green"]
    assert not signal.qualifies
