import pandas as pd

from backend.config.multi_strategy_config import DEFAULT_MULTI_STRATEGY_CONFIG
from backend.divergence.detector import DivergenceSignal
from backend.divergence.swing import SwingPoint
from backend.strategies.runner import ALL_STRATEGY_NAMES, evaluate_all_strategies
from tests.strategy_helpers import make_result


def _bullish_signal() -> DivergenceSignal:
    # PRD's real pattern (Positive Reversal): price higher low, RSI lower
    # low, BOTH legs' RSI above 60 (leg-RSI gate), confirming pivot at bar
    # 98 -> bars_ago=2 against make_result's default last_bar_index=100
    # (within the 7-bar freshness window).
    p1 = SwingPoint(index=78, date=pd.Timestamp("2024-01-10"), price=90.0, kind="low")
    p2 = SwingPoint(index=98, date=pd.Timestamp("2024-02-10"), price=100.0, kind="low")
    return DivergenceSignal(
        kind="hidden_bullish", first_point=p1, second_point=p2,
        first_rsi=65.0, second_rsi=70.0, price_change_pct=11.1, rsi_change=5.0,
    )


def _bearish_signal() -> DivergenceSignal:
    p1 = SwingPoint(index=10, date=pd.Timestamp("2024-01-10"), price=100.0, kind="high")
    p2 = SwingPoint(index=30, date=pd.Timestamp("2024-02-10"), price=110.0, kind="high")
    return DivergenceSignal(
        kind="bearish", first_point=p1, second_point=p2,
        first_rsi=75.0, second_rsi=65.0, price_change_pct=10.0, rsi_change=-10.0,
    )


def _flat_daily_ohlcv(n=60):
    idx = pd.bdate_range("2024-01-01", periods=n)
    values = [100 + (i % 3) for i in range(n)]
    return pd.DataFrame(
        {"open": values, "high": [v + 1 for v in values], "low": [v - 1 for v in values],
         "close": values, "volume": [1000] * n},
        index=idx,
    )


def _daily_ohlcv_with_prd_candle_confirmation(n=60):
    """Same as _flat_daily_ohlcv but the last two bars are a confirmed RED->GREEN breakout (PRD candle confirmation)."""
    df = _flat_daily_ohlcv(n).astype(float)
    df.iloc[-2] = [110.0, 111.0, 107.0, 108.0, 1000.0]  # red: open 110 -> close 108
    df.iloc[-1] = [108.5, 112.5, 108.0, 112.0, 1000.0]  # green: closes above red's high (111.0)
    return df


def test_all_six_strategies_are_returned():
    result = make_result(daily_rsi=40.0, weekly_rsi=65.0, monthly_rsi=70.0, daily_divergences=[_bullish_signal()])
    signals = evaluate_all_strategies(result, _flat_daily_ohlcv(), DEFAULT_MULTI_STRATEGY_CONFIG)
    assert set(signals.keys()) == set(ALL_STRATEGY_NAMES)


def test_stock_can_qualify_for_multiple_strategies_without_deduplication():
    # daily=62 sits inside Advanced GFS's 59-65 band AND clears PRD's ">60"
    # floor; weekly=70/monthly=75 clear both strategies' weekly/monthly gates
    # too (PRD's high-RSI floor is compatible with Advanced GFS's high-RSI
    # band, unlike NRD's low-RSI ceiling).
    result = make_result(daily_rsi=62.0, weekly_rsi=70.0, monthly_rsi=75.0, daily_divergences=[_bullish_signal()])
    signals = evaluate_all_strategies(result, _daily_ohlcv_with_prd_candle_confirmation(), DEFAULT_MULTI_STRATEGY_CONFIG)

    assert signals["Advanced GFS"].qualifies
    assert signals["PRD"].qualifies
    # Each is a distinct, separately-reported signal for the same symbol.
    assert signals["Advanced GFS"].symbol == signals["PRD"].symbol == result.symbol
    assert signals["Advanced GFS"].strategy != signals["PRD"].strategy


def test_non_qualifying_stock_reports_false_everywhere_but_still_present():
    result = make_result(daily_rsi=50.0, weekly_rsi=50.0, monthly_rsi=50.0)
    signals = evaluate_all_strategies(result, _flat_daily_ohlcv(), DEFAULT_MULTI_STRATEGY_CONFIG)
    assert all(not s.qualifies for s in signals.values())
    assert len(signals) == 6
