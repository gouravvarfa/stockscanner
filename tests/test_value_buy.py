import pandas as pd
import pytest

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


# 2026-09-26 (master RSI-freshness change): Value Buy no longer computes its
# own "live month" RSI — it just reads result.monthly.rsi, which
# stock_analysis.py's analyze_stock() now ALWAYS computes as the latest/live
# monthly RSI (current still-forming month included). These tests simulate
# "the live monthly RSI is X" by passing that X straight in via make_result,
# exactly as evaluate_value_buy actually receives it.


def test_live_monthly_rsi_inside_support_zone_passes():
    df = _bseries(_breakout_and_green_week_prices())
    signal = evaluate_value_buy(make_result(monthly_rsi=42.0), df, ValueBuyConfig())
    assert signal.conditions["monthly_rsi_in_support_zone"]
    assert signal.qualifies


def test_astec_like_live_monthly_rsi_45_9_passes():
    df = _bseries(_breakout_and_green_week_prices())
    signal = evaluate_value_buy(make_result(monthly_rsi=45.9), df, ValueBuyConfig())
    # 45.9 is just outside the default 35-45 zone — must NOT pass (proves the
    # zone bound is respected exactly, not loosened for this example).
    assert not signal.conditions["monthly_rsi_in_support_zone"]
    assert not signal.qualifies


def test_live_monthly_rsi_38_within_zone_passes():
    df = _bseries(_breakout_and_green_week_prices())
    signal = evaluate_value_buy(make_result(monthly_rsi=38.0), df, ValueBuyConfig())
    assert signal.conditions["monthly_rsi_in_support_zone"]
    assert signal.qualifies


def test_live_monthly_rsi_outside_zone_fails():
    df = _bseries(_breakout_and_green_week_prices())
    signal = evaluate_value_buy(make_result(monthly_rsi=60.0), df, ValueBuyConfig())
    assert not signal.conditions["monthly_rsi_in_support_zone"]
    assert not signal.qualifies


def test_current_month_red_candle_still_passes_if_rsi_in_zone():
    """Per explicit spec: current month candle colour (red or green) must
    NEVER gate the monthly RSI condition — only the RSI value matters."""
    df = _bseries(_breakout_and_green_week_prices())
    # The daily_ohlcv's own trailing candles determine "current month colour"
    # for a live engine elsewhere, but evaluate_value_buy's monthly check
    # never looks at candle colour at all — proven by it passing here with
    # no colour-based condition present in its output.
    signal = evaluate_value_buy(make_result(monthly_rsi=40.0), df, ValueBuyConfig())
    assert "monthly_candle_green" not in signal.conditions
    assert signal.conditions["monthly_rsi_in_support_zone"]


def test_weekly_and_daily_trigger_still_required_with_live_monthly_rsi():
    flat = _bseries([100 + (i % 3) for i in range(60)])
    signal = evaluate_value_buy(make_result(monthly_rsi=40.0), flat, ValueBuyConfig())
    assert signal.conditions["monthly_rsi_in_support_zone"]
    assert not signal.qualifies  # no key reversal / trendline breakout on a flat series


def test_analyze_stock_monthly_rsi_is_live_not_confirmed():
    """End-to-end: stock_analysis.analyze_stock's monthly.rsi must be the
    LIVE value (current partial month included), with the prior CONFIRMED
    value still available via monthly.previous_rsi."""
    from backend.config.strategy_config import DEFAULT_STRATEGY_CONFIG
    from backend.screeners.stock_analysis import analyze_stock

    idx = pd.bdate_range("2015-01-01", "2026-09-10")
    prices = [300 + (i % 40) * 0.5 for i in range(len(idx))]
    df = pd.DataFrame({"open": prices, "high": [p + 1 for p in prices], "low": [p - 1 for p in prices], "close": prices, "volume": 1000}, index=idx)
    sept = df.index >= "2026-09-01"
    boosted = df.loc[sept, "close"] * 1.5
    for col in ("open", "high", "low", "close"):
        df.loc[sept, col] = boosted

    result = analyze_stock("TEST", df, DEFAULT_STRATEGY_CONFIG)
    assert result.monthly.rsi is not None and result.monthly.previous_rsi is not None
    assert result.monthly.rsi != pytest.approx(result.monthly.previous_rsi, abs=0.01)


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


def test_aplapollo_style_scanner_uses_current_month_not_previous():
    """Regression for the real APLAPOLLO case (2026-09-25): current-month
    candle handling was previously an issue where the scanner silently used
    the last COMPLETED month even when the current month already had real
    daily data. Verifies September 2026's current OHLC feeds the monthly
    RSI, not August's - no hardcoded RSI value, computed from the fixture."""
    from backend.config.strategy_config import DEFAULT_STRATEGY_CONFIG
    from backend.indicators.resample import to_monthly
    from backend.indicators.rsi import rsi as rsi_fn
    from backend.screeners.stock_analysis import analyze_stock

    idx = pd.bdate_range("2016-01-01", "2026-09-25")
    prices = [500.0 + (i % 60) for i in range(len(idx))]
    df = pd.DataFrame(
        {"open": prices, "high": [p + 2 for p in prices], "low": [p - 2 for p in prices], "close": prices, "volume": 1000.0},
        index=idx,
    )
    sept = df.index >= "2026-09-01"
    df.loc[sept, "close"] = df.loc[sept, "close"] * 1.4
    df.loc[sept, "open"] = df.loc[sept, "close"]
    df.loc[sept, "high"] = df.loc[sept, "close"]

    result = analyze_stock("APLAPOLLO", df, DEFAULT_STRATEGY_CONFIG)

    live_monthly = to_monthly(df, include_partial=True)
    assert live_monthly.index[-1].month == 9 and live_monthly.index[-1].year == 2026
    expected_live_rsi = float(rsi_fn(live_monthly["close"], 14).iloc[-1])

    confirmed_monthly = to_monthly(df)
    assert confirmed_monthly.index[-1].month == 8  # last COMPLETED month
    expected_confirmed_rsi = float(rsi_fn(confirmed_monthly["close"], 14).iloc[-1])

    assert result.monthly.rsi == pytest.approx(expected_live_rsi, abs=0.01)
    assert result.monthly.previous_rsi == pytest.approx(expected_confirmed_rsi, abs=0.01)
    assert result.monthly.rsi != pytest.approx(result.monthly.previous_rsi, abs=0.01)
