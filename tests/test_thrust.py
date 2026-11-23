import numpy as np
import pandas as pd

from backend.services import thrust_service as svc


def _frame(closes):
    idx = pd.bdate_range("2024-01-01", periods=len(closes))
    c = np.asarray(closes, dtype=float)
    return pd.DataFrame({"open": c, "high": c + 1, "low": c - 1, "close": c, "volume": 1000.0}, index=idx)


def test_pivots_alternate_and_need_confirmation():
    up = list(np.linspace(100, 140, 40)); down = list(np.linspace(140, 100, 40)); flat = [100.0] * 5
    piv = svc._pivots(*(_frame(up + down + up + flat)[c].to_numpy() for c in ("high", "low")))
    kinds = [k for _, k, _ in piv]
    assert all(a != b for a, b in zip(kinds, kinds[1:]))
    assert all(i <= len(up + down + up + flat) - 1 - svc.STRENGTH for i, _, _ in piv)


def test_fast_rise_after_a_low_is_stretched():
    # slow fall to a low, 10+ quiet bars confirm it, then a run of 8 a day (ATR ~2) for the last 10 bars
    fall = list(np.linspace(150, 100, 60)); base = [100 + (i % 2) * 0.5 for i in range(12)]
    run = [100 + 8 * (i + 1) for i in range(10)]
    out = svc.evaluate(_frame(fall + base + run))
    assert out["direction"] == "up"
    assert out["pace"] > 0
    assert out["status"] in {"stretched", "fired"}


def test_quiet_market_is_normal():
    rng = np.random.default_rng(1)
    closes = 100 + np.cumsum(rng.normal(0, 0.3, 300))
    out = svc.evaluate(_frame(closes))
    assert out["status"] in {"normal", "fired", "stretched"}
    assert out["atr"] > 0 and out["bars_since"] >= svc.STRENGTH
