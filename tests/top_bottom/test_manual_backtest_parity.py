"""
Parity against the user's hand-made ADANIGREEN backtest, which is the
declared source of truth for the Top-Bottom rules.

The decisive rule this locks in: fills happen AT THE LEVEL (System Point
for an entry, stop level for an exit/reversal), never at the close that
crossed it. Every entry and exit price in the manual sheet is a structure
level, and reproducing that exactly is what makes 970.10 -> 804.10 come
out as one continuous +166.00 SELL instead of three whipsaw trades.

The closes below are the real NSE ADANIGREEN daily closes for the stretch
the manual sheet covers — not generated data.
"""
import datetime as dt

import pytest

from backend.strategies.top_bottom.backtest import run_top_bottom_backtest

# Real NSE ADANIGREEN-EQ daily closes, 2025-01-02 .. 2025-05-09, exactly as
# Angel One returned them. The leading bars before the manual sheet starts
# are real warm-up context the structure detection needs.
START_DATE = dt.datetime(2025, 1, 2)
CLOSES = [
    1046.5, 1038.25, 982.6, 1005.5, 988.95, 977.7, 943.05, 889.75, 1006.85,
    1035.05, 1070.25, 1078.2, 1066.75, 1045.7, 1031.7, 1030.25, 1012.1, 998.95,
    987.3, 987.65, 971.85, 997.55, 996.5, 970.1, 983.15, 1017.8, 997.6,
    989.5, 954.05, 946.2, 916.9, 913.75, 884.4, 890.35, 897.55, 864.7,
    864.95, 849.35, 836.05, 840.65, 811.75, 774.4, 804.1, 768.55, 848.7,
    845.95, 837.2, 826.05, 824.2, 853.45, 873.65, 896.45, 900.9, 911.2,
    923.4, 954.25, 952.9, 923.4, 912.1, 959.9, 948.65, 919.15, 943.05,
    955.3, 923.8, 873.3, 875.8, 860.75, 893.65, 936.65, 945.6, 947.15,
    956.25, 943.3, 952.5, 968.95, 912.55, 941.0, 922.4, 900.7, 905.25,
    965.7, 923.25, 917.25, 880.5, 879.45,
]

# (direction, entry level, exit level) exactly as written in the manual sheet.
MANUAL_TRADES = [
    ("SELL", 971, 997),
    ("BUY", 997, 970),
    ("SELL", 970, 804),
    ("BUY", 804, 919),
    ("SELL", 919, 875),
    ("BUY", 875, 943),
    ("SELL", 943, 941),
    ("BUY", 941, 900),
]


def _run():
    base = START_DATE
    dates = [base + dt.timedelta(days=i) for i in range(len(CLOSES))]
    return run_top_bottom_backtest(
        "ADANIGREEN", "ADANIGREEN-EQ", "", "STOCK", 1, dates, CLOSES, CLOSES[:1] + CLOSES[:-1]
    )


def _find(trades, direction, entry, exit_):
    for t in trades:
        if (
            t.direction == direction
            and abs(t.entry_price - entry) < 1.3
            and t.exit_price is not None
            and abs(t.exit_price - exit_) < 1.3
        ):
            return t
    return None


@pytest.mark.parametrize("direction,entry,exit_", MANUAL_TRADES)
def test_engine_reproduces_each_manual_trade(direction, entry, exit_):
    _, trades = _run()
    assert _find(trades, direction, entry, exit_) is not None, (
        f"manual trade {direction} {entry} -> {exit_} not reproduced; "
        f"engine produced {[(t.direction, t.entry_price, t.exit_price) for t in trades]}"
    )


def test_the_970_to_804_case_is_one_continuous_sell_not_three_whipsaws():
    """The regression that motivated the fill-at-level rule."""
    _, trades = _run()
    sell = _find(trades, "SELL", 970.10, 804.10)
    assert sell is not None
    assert round(sell.pnl_points, 2) == 166.00  # manual sheet says +166
    # It must have trailed its stop down through the intervening Tops
    # rather than being stopped out by the 1017.80 bounce.
    stops = [v for _, v in sell.stop_history]
    assert stops == sorted(stops, reverse=True)
    assert stops[0] == 1017.80
    assert stops[-1] == 804.10


def test_every_exit_price_equals_the_next_entry_price():
    """Reversals are one event at one level, so the chain is continuous."""
    _, trades = _run()
    for a, b in zip(trades, trades[1:]):
        if a.exit_reason == "TRAILING_STOP_REVERSAL":
            assert a.exit_price == b.entry_price
