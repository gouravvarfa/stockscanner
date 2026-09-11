from backend.config.multi_strategy_config import AdvancedGFSConfig, GFSConfig
from backend.strategies.advanced_gfs import evaluate_advanced_gfs
from backend.strategies.gfs import evaluate_gfs
from tests.strategy_helpers import make_result


def test_gfs_qualifies_within_band():
    result = make_result(daily_rsi=40.0, weekly_rsi=65.0, monthly_rsi=70.0)
    signal = evaluate_gfs(result, GFSConfig())
    assert signal.qualifies
    assert all(signal.conditions.values())


def test_gfs_rejects_daily_rsi_at_lower_boundary():
    # Spec: strictly > 38, so exactly 38 must fail.
    result = make_result(daily_rsi=38.0, weekly_rsi=65.0, monthly_rsi=70.0)
    signal = evaluate_gfs(result, GFSConfig())
    assert not signal.qualifies
    assert not signal.conditions["daily_rsi_in_band"]


def test_gfs_rejects_daily_rsi_at_upper_boundary():
    result = make_result(daily_rsi=45.0, weekly_rsi=65.0, monthly_rsi=70.0)
    signal = evaluate_gfs(result, GFSConfig())
    assert not signal.qualifies


def test_gfs_rejects_when_weekly_rsi_too_low():
    result = make_result(daily_rsi=40.0, weekly_rsi=55.0, monthly_rsi=70.0)
    signal = evaluate_gfs(result, GFSConfig())
    assert not signal.qualifies
    assert not signal.conditions["weekly_rsi_above_min"]


def test_advanced_gfs_qualifies_within_inclusive_band():
    # Spec uses >= / <= for daily, so boundaries themselves must pass.
    result = make_result(daily_rsi=59.0, weekly_rsi=66.0, monthly_rsi=69.0)
    signal = evaluate_advanced_gfs(result, AdvancedGFSConfig())
    assert signal.qualifies


def test_advanced_gfs_rejects_just_outside_band():
    result = make_result(daily_rsi=58.9, weekly_rsi=66.0, monthly_rsi=69.0)
    signal = evaluate_advanced_gfs(result, AdvancedGFSConfig())
    assert not signal.qualifies


def test_advanced_gfs_rejects_when_monthly_rsi_too_low():
    result = make_result(daily_rsi=60.0, weekly_rsi=66.0, monthly_rsi=68.0)
    signal = evaluate_advanced_gfs(result, AdvancedGFSConfig())
    assert not signal.qualifies
    assert not signal.conditions["monthly_rsi_above_min"]


def test_gfs_and_advanced_gfs_are_independent_signals():
    # A stock could plausibly satisfy neither, either, or in principle be
    # evaluated for both without one suppressing the other.
    result = make_result(daily_rsi=40.0, weekly_rsi=65.0, monthly_rsi=70.0)
    gfs_signal = evaluate_gfs(result, GFSConfig())
    adv_signal = evaluate_advanced_gfs(result, AdvancedGFSConfig())
    assert gfs_signal.qualifies
    assert not adv_signal.qualifies  # daily RSI 40 is outside Advanced GFS's 59-65 band
    assert gfs_signal.strategy != adv_signal.strategy
