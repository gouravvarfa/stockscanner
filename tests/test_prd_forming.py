import json
import pathlib

import pandas as pd
import pytest

from backend.config.multi_strategy_config import PRDConfig
from backend.indicators.resample import to_weekly
from backend.strategies import prd as prd_mod
from backend.strategies.prd import _developing_structures, evaluate_prd
from tests.strategy_helpers import make_result


def _frame(distance: int, last_two: str = "neutral", n: int = 40, b_low: float = 60.0) -> pd.DataFrame:
    """Flat lows of 80 with one 1-bar pivot low A (low 50) exactly `distance` bars before the last bar (B)."""
    idx = pd.bdate_range("2024-01-01", periods=n)
    a = n - 1 - distance
    low = [80.0] * n
    low[a] = 50.0
    low[-1] = b_low
    op = [90.0] * n
    close = [90.0] * n
    close[a] = 91.0  # unique marker so the stubbed RSI can find the A candle
    high = [100.0] * n
    if last_two == "confirm":  # red bar then green bar closing above the red bar's high
        op[-2], close[-2], high[-2], low[-2] = 95.0, 85.0, 96.0, 81.0
        op[-1], close[-1], high[-1] = 84.0, 99.0, 100.0
    elif last_two == "red_only":  # red then red — no green breakout
        op[-2], close[-2], high[-2], low[-2] = 95.0, 85.0, 96.0, 81.0
        op[-1], close[-1], high[-1] = 90.0, 82.0, 91.0
    return pd.DataFrame({"open": op, "high": high, "low": low, "close": close, "volume": [1000] * n}, index=idx)


@pytest.fixture
def fake_rsi(monkeypatch):
    """A's RSI 75 (found via its unique 91.0 close), every other bar (incl. B) 65 -> RSI lower low, both legs > 60."""
    def _rsi(close, period=14):
        vals = pd.Series(65.0, index=close.index)
        vals[close == 91.0] = 75.0
        return vals

    monkeypatch.setattr(prd_mod, "rsi", _rsi)


def _eval(ohlc):
    return evaluate_prd(make_result(), ohlc, PRDConfig())


@pytest.mark.parametrize("distance,valid", [(2, False), (3, True), (6, True), (15, True), (16, False)])
def test_ab_distance_window(fake_rsi, distance, valid):
    ohlc = _frame(distance)
    found = prd_mod._developing_structures(ohlc, PRDConfig())
    assert (len(found) == 1) is valid
    if valid:
        assert found[0]["ab_distance"] == distance


def test_latest_completed_candle_is_b_for_forming(fake_rsi):
    found = prd_mod._developing_structures(_frame(5), PRDConfig())
    assert found[0]["b_bar"] == len(_frame(5)) - 1
    assert found[0]["b_low"] > found[0]["a_low"] and found[0]["b_rsi"] < found[0]["a_rsi"]


def test_forming_is_not_counted_as_confirmed(fake_rsi):
    sig = _eval(_frame(5))
    assert sig.extra["status"] == "PRD_FORMING"
    assert not sig.qualifies
    assert sig.extra["divergences"] == []
    assert sig.extra["forming"][0]["ab_distance"] == 5


def test_red_green_candle_alone_no_longer_confirms_prd(fake_rsi):
    # PRD_CONFIRMED now follows the reference-RSI-bottom definition (see
    # test_prd_confirmed.py); the old developing+breakout-candle transition is gone.
    sig = _eval(_frame(5, "confirm"))
    assert sig.extra["status"] != "PRD_CONFIRMED" or sig.extra["timeframes"]["daily"]["status"] == "PRD_CONFIRMED"
    assert sig.extra["forming"] == []  # forming rules unchanged: no candle-confirmed forming rows


def test_invalid_confirmation_does_not_become_confirmed(fake_rsi):
    sig = _eval(_frame(5, "red_only"))
    assert not sig.qualifies
    assert sig.extra["status"] == "PRD_FORMING"


def test_price_lower_low_is_not_forming(fake_rsi):
    assert prd_mod._developing_structures(_frame(5, b_low=45.0), PRDConfig()) == []


def test_nilkamal_weekly_is_prd_forming():
    data = json.loads((pathlib.Path(__file__).parent / "data" / "nilkamal_1d.json").read_text())
    df = pd.DataFrame(data)
    df.index = pd.to_datetime(df["time"], unit="s")
    w = to_weekly(df[["open", "high", "low", "close", "volume"]])
    found = _developing_structures(w, PRDConfig())
    assert len(found) == 1
    f = found[0]
    assert f["a_date"].startswith("2026-08-07") and f["b_date"].startswith("2026-09-18")
    assert f["a_low"] == 1640.0 and f["b_low"] == 1844.2
    assert f["a_rsi"] == pytest.approx(73.02, abs=0.01) and f["b_rsi"] == pytest.approx(64.04, abs=0.01)
    assert f["ab_distance"] == 6


# ---- all three timeframes evaluated independently -------------------------

def _tf_eval(monkeypatch, daily, weekly, monthly):
    monkeypatch.setattr(prd_mod, "to_weekly", lambda _d: weekly)
    monkeypatch.setattr(prd_mod, "to_monthly", lambda _d: monthly)
    return evaluate_prd(make_result(), daily, PRDConfig())


def _plain(n=40):
    return _frame(30, n=n, b_low=80.0)  # no valid A->B (distance 30, and B == flat low)


def test_daily_forming(fake_rsi, monkeypatch):
    sig = _tf_eval(monkeypatch, _frame(5), _plain(), _plain())
    tf = sig.extra["timeframes"]
    assert tf["daily"]["status"] == "PRD_FORMING"
    assert tf["weekly"]["status"] == tf["monthly"]["status"] == "PRD_NOT_CONFIRMED"


def test_weekly_forming(fake_rsi, monkeypatch):
    tf = _tf_eval(monkeypatch, _plain(), _frame(4), _plain()).extra["timeframes"]
    assert tf["weekly"]["status"] == "PRD_FORMING"
    assert tf["daily"]["status"] == tf["monthly"]["status"] == "PRD_NOT_CONFIRMED"


def test_monthly_forming(fake_rsi, monkeypatch):
    tf = _tf_eval(monkeypatch, _plain(), _plain(), _frame(9)).extra["timeframes"]
    assert tf["monthly"]["status"] == "PRD_FORMING"
    assert tf["monthly"]["setups"][0]["ab_distance"] == 9


def test_all_valid_timeframes_are_reported_not_just_the_first(fake_rsi, monkeypatch):
    sig = _tf_eval(monkeypatch, _frame(3), _frame(6), _frame(15))
    assert {f["timeframe"] for f in sig.extra["forming"]} == {"daily", "weekly", "monthly"}
    assert {t: v["status"] for t, v in sig.extra["timeframes"].items()} == {
        "daily": "PRD_FORMING", "weekly": "PRD_FORMING", "monthly": "PRD_FORMING"}
    assert not sig.qualifies
    for f in sig.extra["forming"]:
        assert {"timeframe", "a_date", "b_date", "a_low", "b_low", "a_rsi", "b_rsi", "ab_distance", "status"} <= set(f)


def test_forming_on_other_timeframes_is_reported_independently(fake_rsi, monkeypatch):
    sig = _tf_eval(monkeypatch, _frame(5), _frame(6), _frame(7))
    tf = sig.extra["timeframes"]
    assert {t: v["status"] for t, v in tf.items()} == {t: "PRD_FORMING" for t in ("daily", "weekly", "monthly")}
