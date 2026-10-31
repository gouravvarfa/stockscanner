import datetime as dt

import pytest

from backend.config.cup_config import CupConfig
from backend.strategies.cup import detect_cup
from backend.strategies.cup_levels import compute_trade_levels, status_group, targets_crossed
from tests.test_cup import _cup_specs, _monthly_frame

CONFIG = CupConfig()


def test_levels_for_neckline_500():
    levels = compute_trade_levels(500.0, CONFIG)
    assert levels == {"entry_price": 520.0, "stop_loss": 490.0, "target_1": 550.0, "target_2": 600.0, "target_3": 650.0}


def test_levels_for_neckline_800():
    levels = compute_trade_levels(800.0, CONFIG)
    assert levels == {"entry_price": 832.0, "stop_loss": 784.0, "target_1": 880.0, "target_2": 960.0, "target_3": 1040.0}


def test_levels_for_the_reference_chart_neckline():
    levels = compute_trade_levels(838.65, CONFIG)
    assert levels["entry_price"] == pytest.approx(872.2, abs=0.2)
    assert levels["stop_loss"] == pytest.approx(821.9, abs=0.4)
    assert levels["target_1"] == pytest.approx(922.5, abs=0.6)


def test_every_target_is_a_percentage_of_the_neckline_not_the_entry():
    levels = compute_trade_levels(1000.0, CONFIG)
    assert levels["target_1"] == 1100.0  # NOT 1040 * 1.10
    assert levels["target_3"] == 1300.0


def test_targets_crossed_counts():
    levels = compute_trade_levels(500.0, CONFIG)
    assert targets_crossed(540.0, levels) == 0
    assert targets_crossed(550.0, levels) == 1
    assert targets_crossed(620.0, levels) == 2
    assert targets_crossed(700.0, levels) == 3


def test_status_groups():
    assert status_group("EARLY_CUP") == "CUP_FORMING"
    assert status_group("NEAR_BREAKOUT") == "AWAITING_BREAKOUT"
    assert status_group("BREAKOUT_FORMING") == "AWAITING_BREAKOUT"
    assert status_group("BREAKOUT_CONFIRMED") == "BREAKOUT_CONFIRMED"
    assert status_group("NO_SIGNAL") is None


def test_detect_cup_attaches_levels_from_the_stocks_own_neckline():
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=600.0, recovery_close=850.0)
    result = detect_cup(_monthly_frame(specs), CONFIG, now=dt.datetime(y, m, 10))
    assert result["status"] == "EARLY_CUP"
    assert result["status_group"] == "CUP_FORMING"
    assert result["neckline"] == pytest.approx(1000.0)
    assert result["entry_price"] == pytest.approx(1040.0)
    assert result["stop_loss"] == pytest.approx(980.0)
    assert result["target_1"] == pytest.approx(1100.0)
    assert result["target_2"] == pytest.approx(1200.0)
    assert result["target_3"] == pytest.approx(1300.0)
    assert result["cup_start_date"] == result["left_rim_date"]


def test_neckline_approaching_is_awaiting_breakout_not_confirmed():
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=600.0, recovery_close=960.0)
    result = detect_cup(_monthly_frame(specs), CONFIG, now=dt.datetime(y, m, 10))
    assert result["status"] == "NEAR_BREAKOUT"
    assert result["status_group"] == "AWAITING_BREAKOUT"


def test_completed_close_above_neckline_is_breakout_confirmed_group():
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=600.0, recovery_close=1030.0)
    result = detect_cup(_monthly_frame(specs), CONFIG, now=dt.datetime(y, m, 10))
    # The linear recovery closed above the neckline a couple of months ago,
    # so the detailed status is RECENT_BREAKOUT — same group.
    assert result["status"] in ("BREAKOUT_CONFIRMED", "RECENT_BREAKOUT")
    assert result["status_group"] == "BREAKOUT_CONFIRMED"
    assert result["neckline"] == pytest.approx(1000.0)


def test_cup_with_fewer_than_five_years_is_rejected():
    # left rim -> now = 11 + 10 + 10 completed months: far under 60.
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=600.0, recovery_close=900.0, n_decline=10, n_recover=10, n_lead=12)
    result = detect_cup(_monthly_frame(specs), CONFIG, now=dt.datetime(y, m, 10))
    assert result["status"] in ("NO_SIGNAL", "INSUFFICIENT_HISTORY")
    assert "entry_price" not in result


def test_cup_of_exactly_five_years_is_accepted():
    # rim + 30 decline + 30 recover -> rim is ~60 completed months back.
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=600.0, recovery_close=850.0, n_decline=30, n_recover=30)
    result = detect_cup(_monthly_frame(specs), CONFIG, now=dt.datetime(y, m, 10))
    assert result["status"] == "EARLY_CUP"
    assert result["cup_age_months"] >= 60


def test_cup_longer_than_five_years_is_accepted():
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=600.0, recovery_close=850.0, n_decline=48, n_recover=48)
    result = detect_cup(_monthly_frame(specs), CONFIG, now=dt.datetime(y, m, 10))
    assert result["status"] == "EARLY_CUP"
    assert result["cup_age_years"] > 5


def test_cup_with_59_months_is_rejected():
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=600.0, recovery_close=850.0, n_decline=30, n_recover=29)
    result = detect_cup(_monthly_frame(specs), CONFIG, now=dt.datetime(y, m, 10))
    assert result["status"] == "NO_SIGNAL"


def test_empty_or_missing_data_is_not_a_signal():
    import pandas as pd

    empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    result = detect_cup(empty, CONFIG)
    assert result["status"] == "INSUFFICIENT_HISTORY"
    assert "entry_price" not in result


def test_cup_without_a_prior_uptrend_is_accepted_by_default():
    # A bear-market-style lead-in (falling before the rim) used to be
    # rejected as "no_established_uptrend_before_cup"; the uptrend rule is
    # now off, so the cup alone decides.
    from tests.test_cup import _cup_specs as cup_specs

    specs, (y, m) = cup_specs(left_rim=1000.0, cup_low=600.0, recovery_close=850.0)
    # Replace the rising lead-in with a falling one.
    for i in range(12):
        price = 900.0 - i * 15
        specs[i] = (specs[i][0], specs[i][1], price, price, price, price, 1000.0)
    result = detect_cup(_monthly_frame(specs), CONFIG, now=dt.datetime(y, m, 10))
    assert result["status"] == "EARLY_CUP"
    assert result["trend_before_cup"] is None
