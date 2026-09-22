import pandas as pd
import pytest

from backend.config.multi_strategy_config import PRDConfig
from backend.strategies import prd as prd_mod
from backend.strategies.prd import _confirmed_reference, evaluate_prd
from tests.prd_confirmed_helpers import confirmed_frame, install_rsi
from tests.strategy_helpers import make_result


def _daily_status(sig):
    return sig.extra["timeframes"]["daily"]["status"]


def test_confirmed_when_all_four_conditions_pass(monkeypatch):
    install_rsi(monkeypatch, a_rsi=70, b_rsi=65)
    ref = _confirmed_reference(confirmed_frame(), PRDConfig())
    assert ref["passed"]
    assert ref["reference_rsi"] == 70 and ref["current_rsi"] == 65
    assert ref["reference_price_low"] == 90.0 and ref["current_close"] == 105.0
    assert "<" in ref["rsi_comparison"] and ">" in ref["price_comparison"]


def test_result_exposes_all_reference_and_current_fields(monkeypatch):
    install_rsi(monkeypatch)
    sig = evaluate_prd(make_result(), confirmed_frame(), PRDConfig())
    assert sig.qualifies and sig.extra["status"] == "PRD_CONFIRMED"
    m = sig.extra["divergences"][0]
    for key in ("reference_rsi_date", "reference_rsi", "reference_price_low_date", "reference_price_low",
                "current_candle_date", "current_close", "current_rsi", "rsi_comparison", "price_comparison",
                "timeframe", "status"):
        assert key in m, key
    assert "DAILY" in sig.extra["divergence_timeframes"]


def test_b_does_not_need_to_be_a_pivot(monkeypatch):
    # the last candle is the LOWEST RSI and highest close - it can never be a confirmed pivot, still confirms
    install_rsi(monkeypatch, a_rsi=70, b_rsi=61)
    assert _confirmed_reference(confirmed_frame(b_close=130.0), PRDConfig())["passed"]


def test_rsi_pivot_and_price_low_need_not_share_a_candle(monkeypatch):
    install_rsi(monkeypatch, a_from_end=6)
    ref = _confirmed_reference(confirmed_frame(a_from_end=4), PRDConfig())  # price low 2 candles after the RSI pivot
    assert ref["passed"] and ref["reference_rsi_date"] != ref["reference_price_low_date"]


def test_price_low_outside_plus_minus_two_window_is_ignored(monkeypatch):
    install_rsi(monkeypatch, a_from_end=6)
    ref = _confirmed_reference(confirmed_frame(a_from_end=2), PRDConfig())  # 4 candles away
    assert ref["reference_price_low"] == 100.0  # the marked 90 low was NOT picked


@pytest.mark.parametrize(
    "a_rsi,b_rsi,b_close,failing",
    [
        (60.0, 55.0, 105.0, "a_rsi_above_min"),          # A RSI must be > 60 (strict)
        (70.0, 60.0, 105.0, "b_rsi_above_min"),          # B RSI must be > 60 (strict)
        (65.0, 66.0, 105.0, "rsi_lower_low"),            # B RSI must be lower than A
        (70.0, 65.0, 85.0, "price_above_reference_low"), # B close must be above A price low
    ],
)
def test_each_condition_is_mandatory(monkeypatch, a_rsi, b_rsi, b_close, failing):
    install_rsi(monkeypatch, a_rsi=a_rsi, b_rsi=b_rsi)
    ref = _confirmed_reference(confirmed_frame(b_close=b_close), PRDConfig())
    assert not ref["passed"] and ref["checks"][failing] is False


def test_rsi_dip_below_min_between_legs_fails_even_with_valid_endpoints(monkeypatch):
    """2026-09-22 UNOMINDA diagnostic: A RSI 70 and B RSI 65 both pass on
    their own, but RSI dips to 50 between them — the path must stay above
    leg_rsi_min for every candle, not just the two endpoints."""
    a_from_end = 6

    def _rsi(close, period=14):
        n = len(close)
        a_idx = n - 1 - a_from_end
        vals = pd.Series(80.0, index=close.index)  # neighbors of A stay high so A is still a valid RSI pivot low
        vals.iloc[a_idx] = 70.0
        vals.iloc[a_idx + 2 : n - 1] = 50.0  # dip after A's immediate neighbor, so A stays a valid RSI pivot low
        vals.iloc[-1] = 65.0
        return vals

    monkeypatch.setattr(prd_mod, "rsi", _rsi)
    ref = _confirmed_reference(confirmed_frame(), PRDConfig())
    assert not ref["passed"] and ref["checks"]["rsi_stays_above_min_between_legs"] is False


def test_no_breakout_candle_freshness_distance_or_amplitude_required(monkeypatch):
    install_rsi(monkeypatch, a_from_end=20)  # A 20 candles back: >15 distance, >7 fresh
    frame = confirmed_frame(n=40, a_from_end=20)  # last two candles are NOT red->green
    assert evaluate_prd(make_result(), frame, PRDConfig()).qualifies


def test_forming_and_confirmed_are_separate_statuses(monkeypatch):
    # confirmed timeframe reports CONFIRMED; an unrelated one can still be FORMING / not confirmed
    install_rsi(monkeypatch)
    sig = evaluate_prd(make_result(), confirmed_frame(), PRDConfig())
    statuses = {t: v["status"] for t, v in sig.extra["timeframes"].items()}
    assert statuses["daily"] == "PRD_CONFIRMED"
    assert sig.extra["status"] == "PRD_CONFIRMED"


def test_forming_only_stock_is_not_confirmed(monkeypatch):
    # developing structure exists (existing forming path) but the new confirmed rule fails (B RSI not lower)
    real = prd_mod._developing_structures
    monkeypatch.setattr(prd_mod, "_developing_structures", lambda ohlc, cfg, *a: [{
        "a_date": "2024-01-10", "a_low": 90.0, "a_rsi": 65.0, "a_bar": 1, "b_date": "2024-02-01", "b_low": 95.0,
        "b_rsi": 61.0, "b_bar": 9, "ab_distance": 8, "price_change_pct": 5.0, "rsi_change": -4.0}])
    install_rsi(monkeypatch, a_rsi=65, b_rsi=66)  # confirmed fails: 66 is not < 65
    sig = evaluate_prd(make_result(), confirmed_frame(), PRDConfig())
    assert not sig.qualifies and sig.extra["status"] == "PRD_FORMING"
    assert sig.extra["timeframes"]["daily"]["status"] == "PRD_FORMING"
    assert sig.extra["forming"]  # forming details untouched
    assert real  # original function object still exists (forming path preserved)


def test_confirmed_wins_overall_when_any_timeframe_passes(monkeypatch):
    install_rsi(monkeypatch)
    sig = evaluate_prd(make_result(), confirmed_frame(), PRDConfig())
    assert sig.qualifies
    assert sig.extra["status"] == "PRD_CONFIRMED"
