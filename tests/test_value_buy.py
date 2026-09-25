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


import backend.strategies.value_buy as vb


def _live(monkeypatch, live, peak, green):
    monkeypatch.setattr(vb, "_live_month_rsi", lambda df: (live, peak, green))


def test_prev_rsi_38_live_42_green_month_passes(monkeypatch):
    _live(monkeypatch, 42.0, 42.0, True)
    df = _bseries(_breakout_and_green_week_prices())
    signal = evaluate_value_buy(make_result(monthly_rsi=38.0), df, ValueBuyConfig())
    assert signal.conditions["live_month_green_and_rsi_crossed_40"]
    assert signal.qualifies
    assert signal.extra["live_month"] is True


def test_astec_like_live_46_after_crossing_40_passes(monkeypatch):
    _live(monkeypatch, 45.9, 46.0, True)
    df = _bseries(_breakout_and_green_week_prices())
    signal = evaluate_value_buy(make_result(monthly_rsi=38.1), df, ValueBuyConfig())
    assert signal.qualifies


def test_touched_40_then_dipped_below_still_passes(monkeypatch):
    _live(monkeypatch, 39.0, 41.0, True)
    df = _bseries(_breakout_and_green_week_prices())
    assert evaluate_value_buy(make_result(monthly_rsi=37.0), df, ValueBuyConfig()).conditions[
        "live_month_green_and_rsi_crossed_40"
    ]


def test_red_current_month_fails(monkeypatch):
    _live(monkeypatch, 45.0, 46.0, False)
    df = _bseries(_breakout_and_green_week_prices())
    signal = evaluate_value_buy(make_result(monthly_rsi=38.0), df, ValueBuyConfig())
    assert not signal.conditions["live_month_green_and_rsi_crossed_40"]
    assert not signal.qualifies


def test_rsi_never_reached_40_fails(monkeypatch):
    _live(monkeypatch, 35.0, 38.0, True)
    df = _bseries(_breakout_and_green_week_prices())
    assert not evaluate_value_buy(make_result(monthly_rsi=35.0), df, ValueBuyConfig()).qualifies


def test_weekly_and_daily_trigger_still_required(monkeypatch):
    _live(monkeypatch, 45.0, 46.0, True)
    flat = _bseries([100 + (i % 3) for i in range(60)])
    signal = evaluate_value_buy(make_result(monthly_rsi=38.0), flat, ValueBuyConfig())
    assert signal.conditions["live_month_green_and_rsi_crossed_40"]
    assert not signal.qualifies


def test_live_month_rsi_uses_current_partial_month():
    # 20 months of steady decline then a partial month rallying: live RSI must
    # reflect the partial month, and the month must read as green.
    idx = pd.bdate_range("2024-01-01", "2025-09-10")
    prices = [300 - i * 0.2 for i in range(len(idx))]
    df = pd.DataFrame({"open": prices, "high": prices, "low": prices, "close": prices, "volume": 1}, index=idx)
    sept = df.index >= "2025-09-01"
    df.loc[sept, "close"] = df.loc[sept, "close"] * 1.3
    df.loc[sept, "high"] = df.loc[sept, "close"]
    live, peak, green = vb._live_month_rsi(df)
    assert green and peak >= live and live > 30


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
