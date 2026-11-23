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


def test_angle_fan_halves_the_swing_angle():
    import math
    import numpy as np
    import pandas as pd
    from backend.strategies import gann_time as g

    idx = pd.bdate_range("2025-01-01", periods=60)
    close = np.r_[np.linspace(100, 130, 31), np.linspace(129, 115, 29)]
    df = pd.DataFrame({"open": close, "high": close + 1, "low": close - 1, "close": close}, index=idx)
    piv = [g.Pivot(0, "L", idx[0].date(), 99.0), g.Pivot(30, "H", idx[30].date(), 131.0)]
    fan = g.angle_fan(df, piv)
    assert fan is not None and fan.origin_price == 99.0
    by = {l.fraction: l for l in fan.lines}
    assert math.isclose(by[0.5].degrees, fan.degrees / 2)
    assert math.isclose(by[0.25].degrees, fan.degrees / 4)
    assert by[0].slope == 0 and by[-0.5].slope == -by[0.5].slope
    assert math.isclose(by[1].slope * 30 + 99, 131.0)
