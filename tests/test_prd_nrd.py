import pandas as pd

from backend.config.multi_strategy_config import NRDConfig, PRDConfig
from backend.divergence.detector import DivergenceSignal
from backend.divergence.swing import SwingPoint
from backend.strategies.nrd import evaluate_nrd
from backend.strategies.prd import evaluate_prd
from tests.strategy_helpers import make_result


def _bullish_signal() -> DivergenceSignal:
    p1 = SwingPoint(index=10, date=pd.Timestamp("2024-01-10"), price=100.0, kind="low")
    p2 = SwingPoint(index=30, date=pd.Timestamp("2024-02-10"), price=90.0, kind="low")  # lower low
    return DivergenceSignal(
        kind="bullish", first_point=p1, second_point=p2,
        first_rsi=25.0, second_rsi=35.0,  # higher RSI low -> bullish divergence
        price_change_pct=-10.0, rsi_change=10.0,
    )


def _bearish_signal() -> DivergenceSignal:
    p1 = SwingPoint(index=10, date=pd.Timestamp("2024-01-10"), price=100.0, kind="high")
    p2 = SwingPoint(index=30, date=pd.Timestamp("2024-02-10"), price=110.0, kind="high")  # higher high
    return DivergenceSignal(
        kind="bearish", first_point=p1, second_point=p2,
        first_rsi=75.0, second_rsi=65.0,  # lower RSI high -> bearish divergence
        price_change_pct=10.0, rsi_change=-10.0,
    )


# PRD = uptrend context -> each timeframe's own RSI gate is a FLOOR (>60).
_HIGH_RSI = dict(daily_rsi=65.0, weekly_rsi=62.0, monthly_rsi=61.0)
# NRD = downtrend context -> each timeframe's own RSI gate is a CEILING (<45).
_LOW_RSI = dict(daily_rsi=35.0, weekly_rsi=38.0, monthly_rsi=40.0)


# ---------------------------------------------------------------------------
# PRD: qualifies on ANY ONE (or more) of daily/weekly/monthly independently.
# ---------------------------------------------------------------------------

def test_prd_daily_only_included():
    result = make_result(**_HIGH_RSI, daily_divergences=[_bullish_signal()])
    signal = evaluate_prd(result, PRDConfig())
    assert signal.qualifies
    assert signal.extra["divergence_timeframes"] == ["DAILY"]


def test_prd_weekly_only_included():
    result = make_result(**_HIGH_RSI, weekly_divergences=[_bullish_signal()])
    signal = evaluate_prd(result, PRDConfig())
    assert signal.qualifies
    assert signal.extra["divergence_timeframes"] == ["WEEKLY"]


def test_prd_monthly_only_included():
    result = make_result(**_HIGH_RSI, monthly_divergences=[_bullish_signal()])
    signal = evaluate_prd(result, PRDConfig())
    assert signal.qualifies
    assert signal.extra["divergence_timeframes"] == ["MONTHLY"]


def test_prd_daily_and_weekly_included():
    result = make_result(**_HIGH_RSI, daily_divergences=[_bullish_signal()], weekly_divergences=[_bullish_signal()])
    signal = evaluate_prd(result, PRDConfig())
    assert signal.qualifies
    assert signal.extra["divergence_timeframes"] == ["DAILY", "WEEKLY"]


def test_prd_weekly_and_monthly_included():
    result = make_result(**_HIGH_RSI, weekly_divergences=[_bullish_signal()], monthly_divergences=[_bullish_signal()])
    signal = evaluate_prd(result, PRDConfig())
    assert signal.qualifies
    assert signal.extra["divergence_timeframes"] == ["WEEKLY", "MONTHLY"]


def test_prd_daily_and_monthly_included():
    result = make_result(**_HIGH_RSI, daily_divergences=[_bullish_signal()], monthly_divergences=[_bullish_signal()])
    signal = evaluate_prd(result, PRDConfig())
    assert signal.qualifies
    assert signal.extra["divergence_timeframes"] == ["DAILY", "MONTHLY"]


def test_prd_all_three_included():
    result = make_result(
        **_HIGH_RSI,
        daily_divergences=[_bullish_signal()],
        weekly_divergences=[_bullish_signal()],
        monthly_divergences=[_bullish_signal()],
    )
    signal = evaluate_prd(result, PRDConfig())
    assert signal.qualifies
    assert signal.extra["divergence_timeframes"] == ["DAILY", "WEEKLY", "MONTHLY"]


def test_prd_no_divergence_anywhere_excluded():
    result = make_result(**_HIGH_RSI)
    signal = evaluate_prd(result, PRDConfig())
    assert not signal.qualifies
    assert signal.extra["divergence_timeframes"] == []


def test_prd_divergence_timeframe_not_coupled_to_other_timeframes_rsi():
    # Daily has a bullish divergence and passes ITS OWN RSI floor, even
    # though weekly/monthly RSI are in the NRD-like (low) zone and have no
    # divergence at all. Must still qualify via daily alone.
    result = make_result(daily_rsi=65.0, weekly_rsi=30.0, monthly_rsi=30.0, daily_divergences=[_bullish_signal()])
    signal = evaluate_prd(result, PRDConfig())
    assert signal.qualifies
    assert signal.extra["divergence_timeframes"] == ["DAILY"]


def test_prd_ignores_bearish_signals():
    result = make_result(**_HIGH_RSI, daily_divergences=[_bearish_signal()])
    signal = evaluate_prd(result, PRDConfig())
    assert not signal.qualifies


def test_prd_rejects_when_rsi_too_low_on_the_only_divergent_timeframe():
    # Divergence present on daily, but daily's own RSI fails PRD's floor —
    # must not qualify even though daily has a divergence signal.
    result = make_result(**_LOW_RSI, daily_divergences=[_bullish_signal()])
    signal = evaluate_prd(result, PRDConfig())
    assert not signal.qualifies
    assert signal.conditions["daily_bullish_divergence"]
    assert not signal.conditions["daily_rsi_above_min"]


# ---------------------------------------------------------------------------
# NRD: qualifies on ANY ONE (or more) of daily/weekly/monthly independently.
# ---------------------------------------------------------------------------

def test_nrd_daily_only_included():
    result = make_result(**_LOW_RSI, daily_divergences=[_bearish_signal()])
    signal = evaluate_nrd(result, NRDConfig())
    assert signal.qualifies
    assert signal.extra["divergence_timeframes"] == ["DAILY"]


def test_nrd_weekly_only_included():
    result = make_result(**_LOW_RSI, weekly_divergences=[_bearish_signal()])
    signal = evaluate_nrd(result, NRDConfig())
    assert signal.qualifies
    assert signal.extra["divergence_timeframes"] == ["WEEKLY"]


def test_nrd_monthly_only_included():
    result = make_result(**_LOW_RSI, monthly_divergences=[_bearish_signal()])
    signal = evaluate_nrd(result, NRDConfig())
    assert signal.qualifies
    assert signal.extra["divergence_timeframes"] == ["MONTHLY"]


def test_nrd_daily_and_weekly_included():
    result = make_result(**_LOW_RSI, daily_divergences=[_bearish_signal()], weekly_divergences=[_bearish_signal()])
    signal = evaluate_nrd(result, NRDConfig())
    assert signal.qualifies
    assert signal.extra["divergence_timeframes"] == ["DAILY", "WEEKLY"]


def test_nrd_weekly_and_monthly_included():
    result = make_result(**_LOW_RSI, weekly_divergences=[_bearish_signal()], monthly_divergences=[_bearish_signal()])
    signal = evaluate_nrd(result, NRDConfig())
    assert signal.qualifies
    assert signal.extra["divergence_timeframes"] == ["WEEKLY", "MONTHLY"]


def test_nrd_daily_and_monthly_included():
    result = make_result(**_LOW_RSI, daily_divergences=[_bearish_signal()], monthly_divergences=[_bearish_signal()])
    signal = evaluate_nrd(result, NRDConfig())
    assert signal.qualifies
    assert signal.extra["divergence_timeframes"] == ["DAILY", "MONTHLY"]


def test_nrd_all_three_included():
    result = make_result(
        **_LOW_RSI,
        daily_divergences=[_bearish_signal()],
        weekly_divergences=[_bearish_signal()],
        monthly_divergences=[_bearish_signal()],
    )
    signal = evaluate_nrd(result, NRDConfig())
    assert signal.qualifies
    assert signal.extra["divergence_timeframes"] == ["DAILY", "WEEKLY", "MONTHLY"]


def test_nrd_no_divergence_anywhere_excluded():
    result = make_result(**_LOW_RSI)
    signal = evaluate_nrd(result, NRDConfig())
    assert not signal.qualifies
    assert signal.extra["divergence_timeframes"] == []


def test_nrd_divergence_timeframe_not_coupled_to_other_timeframes_rsi():
    result = make_result(daily_rsi=35.0, weekly_rsi=70.0, monthly_rsi=70.0, daily_divergences=[_bearish_signal()])
    signal = evaluate_nrd(result, NRDConfig())
    assert signal.qualifies
    assert signal.extra["divergence_timeframes"] == ["DAILY"]


def test_nrd_ignores_bullish_signals():
    result = make_result(**_LOW_RSI, weekly_divergences=[_bullish_signal()])
    signal = evaluate_nrd(result, NRDConfig())
    assert not signal.qualifies


def test_nrd_rejects_when_rsi_too_high_on_the_only_divergent_timeframe():
    result = make_result(**_HIGH_RSI, weekly_divergences=[_bearish_signal()])
    signal = evaluate_nrd(result, NRDConfig())
    assert not signal.qualifies
    assert signal.conditions["weekly_bearish_divergence"]
    assert not signal.conditions["weekly_rsi_below_max"]


# ---------------------------------------------------------------------------
# Separation: PRD and NRD must never satisfy each other, even on the same
# stock with different timeframes triggering each.
# ---------------------------------------------------------------------------

def test_daily_prd_and_weekly_nrd_appear_separately():
    result = make_result(
        daily_rsi=65.0, weekly_rsi=40.0, monthly_rsi=50.0,
        daily_divergences=[_bullish_signal()], weekly_divergences=[_bearish_signal()],
    )
    prd_signal = evaluate_prd(result, PRDConfig())
    nrd_signal = evaluate_nrd(result, NRDConfig())

    assert prd_signal.qualifies
    assert prd_signal.extra["divergence_timeframes"] == ["DAILY"]
    assert nrd_signal.qualifies
    assert nrd_signal.extra["divergence_timeframes"] == ["WEEKLY"]
    assert prd_signal.strategy != nrd_signal.strategy


def test_prd_never_satisfies_nrd():
    # A pure bullish-divergence, high-RSI stock -> PRD qualifies, NRD must not.
    result = make_result(**_HIGH_RSI, daily_divergences=[_bullish_signal()])
    prd_signal = evaluate_prd(result, PRDConfig())
    nrd_signal = evaluate_nrd(result, NRDConfig())
    assert prd_signal.qualifies
    assert not nrd_signal.qualifies


def test_nrd_never_satisfies_prd():
    # A pure bearish-divergence, low-RSI stock -> NRD qualifies, PRD must not.
    result = make_result(**_LOW_RSI, daily_divergences=[_bearish_signal()])
    prd_signal = evaluate_prd(result, PRDConfig())
    nrd_signal = evaluate_nrd(result, NRDConfig())
    assert not prd_signal.qualifies
    assert nrd_signal.qualifies
