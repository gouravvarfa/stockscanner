import datetime as dt

import numpy as np
import pandas as pd

from backend.services.gann_time_service import evaluate, search_nse
from backend.strategies import gann_time as g


def _wave(n=400, period=60):
    idx = pd.bdate_range("2024-01-01", periods=n)
    base = 100 + 10 * np.sin(np.arange(n) * 2 * np.pi / period)
    return pd.DataFrame({"open": base, "high": base + 1, "low": base - 1, "close": base}, index=idx)


def test_pivots_alternate():
    df = _wave()
    piv = g.find_pivots(df["high"].to_numpy(), df["low"].to_numpy())
    kinds = [k for _, k in piv]
    assert len(piv) >= 8
    assert all(a != b for a, b in zip(kinds, kinds[1:]))


def test_projection_math():
    p = {x.label: x.bar for x in g.project(100, 130, dt.date(2024, 1, 1))}
    assert p["1x"] == 160 and p["2x"] == 190 and p["0.5x"] == 145
    assert p["SQ9 180°"] == 100 + round((30 ** 0.5 + 0.5) ** 2)


def test_regular_cycle_gives_cluster_at_next_turn():
    # Perfect 60-bar cycle: every count is a multiple of 30, so projections agree.
    res = g.analyse(_wave())
    assert res is not None and res.clusters
    c = res.clusters[0]
    assert c.strength >= 2
    assert -g.WINDOW_BARS <= c.bars_away <= g.HORIZON_BARS


def test_evaluate_row_and_search():
    row = evaluate("TEST", _wave())
    assert row.ret_1m is not None and row.clusters
    assert search_nse("divis")[0]["symbol"] == "DIVISLAB"


def test_commodities_are_searchable_and_named():
    from backend.services.gann_time_service import company_name, is_commodity

    assert search_nse("gold")[0]["symbol"] == "GOLD"
    assert search_nse("crude")[0]["symbol"] == "CRUDEOIL"
    assert is_commodity("naturalgas") and not is_commodity("RELIANCE")
    assert company_name("CRUDEOIL") == "Crude Oil (MCX futures)"
