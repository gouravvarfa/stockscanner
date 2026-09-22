import pandas as pd
import pytest

from backend.config.multi_strategy_config import NRDConfig
from backend.strategies import nrd as nrd_mod
from backend.strategies.nrd import _developing_structures, evaluate_nrd
from tests.strategy_helpers import make_result


def _frame(distance: int, n: int = 40, b_high: float = 90.0) -> pd.DataFrame:
    """Flat highs of 100 with one 1-bar pivot high A (high 150) exactly `distance` bars before the last bar (B)."""
    idx = pd.bdate_range("2024-01-01", periods=n)
    a = n - 1 - distance
    high = [100.0] * n
    high[a] = 150.0
    high[-1] = b_high
    op = [90.0] * n
    close = [90.0] * n
    close[a] = 91.0  # unique marker so the stubbed RSI can find the A candle
    low = [80.0] * n
    return pd.DataFrame({"open": op, "high": high, "low": low, "close": close, "volume": [1000] * n}, index=idx)


@pytest.fixture
def fake_rsi(monkeypatch):
    """A's RSI 25 (found via its unique 91.0 close), every other bar (incl. B) 35 -> RSI higher high, both legs < 40."""
    def _rsi(close, period=14):
        vals = pd.Series(35.0, index=close.index)
        vals[close == 91.0] = 25.0
        return vals

    monkeypatch.setattr(nrd_mod, "rsi", _rsi)


def _eval(ohlc):
    return evaluate_nrd(make_result(), ohlc, NRDConfig())


@pytest.mark.parametrize("distance,valid", [(2, False), (3, True), (6, True), (15, True), (16, False)])
def test_ab_distance_window(fake_rsi, distance, valid):
    ohlc = _frame(distance)
    found = nrd_mod._developing_structures(ohlc, NRDConfig())
    assert (len(found) == 1) is valid
    if valid:
        assert found[0]["ab_distance"] == distance


def test_latest_completed_candle_is_b_for_forming(fake_rsi):
    found = nrd_mod._developing_structures(_frame(5), NRDConfig())
    assert found[0]["b_bar"] == len(_frame(5)) - 1
    assert found[0]["b_high"] < found[0]["a_high"] and found[0]["b_rsi"] > found[0]["a_rsi"]


def test_forming_is_not_counted_as_confirmed(fake_rsi):
    sig = _eval(_frame(5))
    assert sig.extra["status"] == "NRD_FORMING"
    assert not sig.qualifies
    assert sig.extra["divergences"] == []
    assert sig.extra["forming"][0]["ab_distance"] == 5


def test_price_higher_high_is_not_forming(fake_rsi):
    assert nrd_mod._developing_structures(_frame(5, b_high=160.0), NRDConfig()) == []


def test_rsi_rise_above_max_between_legs_is_not_forming(monkeypatch):
    """Mirrors the UNOMINDA-style PRD fix (2026-09-22): A RSI 25, B RSI 35
    (both endpoints below leg_rsi_max=40), but RSI spikes to 55 mid-way
    between them. Both endpoints alone used to pass; the path must now also
    stay below 40 for the whole A->B run."""
    ohlc = _frame(6)

    def _rsi(close, period=14):
        vals = pd.Series(35.0, index=close.index)
        vals[close == 91.0] = 25.0  # A
        vals.iloc[-1] = 35.0  # B, still < 40
        mid = len(vals) - 4
        vals.iloc[mid] = 55.0  # spikes above leg_rsi_max between A and B
        return vals

    monkeypatch.setattr(nrd_mod, "rsi", _rsi)
    assert nrd_mod._developing_structures(ohlc, NRDConfig()) == []


# ---- all three timeframes evaluated independently -------------------------

def _tf_eval(monkeypatch, daily, weekly, monthly):
    monkeypatch.setattr(nrd_mod, "to_weekly", lambda _d: weekly)
    monkeypatch.setattr(nrd_mod, "to_monthly", lambda _d: monthly)
    return evaluate_nrd(make_result(), daily, NRDConfig())


def _plain(n=40):
    return _frame(30, n=n, b_high=100.0)  # no valid A->B (distance 30, and B == flat high)


def test_daily_forming(fake_rsi, monkeypatch):
    sig = _tf_eval(monkeypatch, _frame(5), _plain(), _plain())
    tf = sig.extra["timeframes"]
    assert tf["daily"]["status"] == "NRD_FORMING"
    assert tf["weekly"]["status"] == tf["monthly"]["status"] == "NRD_NOT_CONFIRMED"


def test_weekly_forming(fake_rsi, monkeypatch):
    tf = _tf_eval(monkeypatch, _plain(), _frame(4), _plain()).extra["timeframes"]
    assert tf["weekly"]["status"] == "NRD_FORMING"
    assert tf["daily"]["status"] == tf["monthly"]["status"] == "NRD_NOT_CONFIRMED"


def test_monthly_forming(fake_rsi, monkeypatch):
    tf = _tf_eval(monkeypatch, _plain(), _plain(), _frame(9)).extra["timeframes"]
    assert tf["monthly"]["status"] == "NRD_FORMING"
    assert tf["monthly"]["setups"][0]["ab_distance"] == 9


def test_all_valid_timeframes_are_reported_not_just_the_first(fake_rsi, monkeypatch):
    sig = _tf_eval(monkeypatch, _frame(3), _frame(6), _frame(15))
    assert {f["timeframe"] for f in sig.extra["forming"]} == {"daily", "weekly", "monthly"}
    assert {t: v["status"] for t, v in sig.extra["timeframes"].items()} == {
        "daily": "NRD_FORMING", "weekly": "NRD_FORMING", "monthly": "NRD_FORMING"}
    assert not sig.qualifies
    for f in sig.extra["forming"]:
        assert {"timeframe", "a_date", "b_date", "a_high", "b_high", "a_rsi", "b_rsi", "ab_distance", "status"} <= set(f)
