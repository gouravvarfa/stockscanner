"""
The spec's MANDATORY end-to-end sequence. Verifies that Tops/Bottoms are
treated as STRUCTURE, never as direct BUY/SELL signals — the engine must
produce exactly:

    BUY ENTRY -> trailing BUY SL updates -> BUY EXIT
    -> SELL ENTRY -> trailing SELL SL updates -> SELL EXIT -> BUY ENTRY

and NOT one entry per detected Top/Bottom.
"""
import datetime as dt

from backend.strategies.top_bottom.backtest import run_top_bottom_backtest

MANDATORY_CLOSES = [
    100, 80, 90, 85, 95, 110, 100, 120, 108, 130, 115, 107,
    90, 80, 85, 70, 79, 65, 70, 55, 62, 45, 55, 63,
]


def _run(closes):
    base = dt.datetime(2026, 1, 1)
    dates = [base + dt.timedelta(days=i) for i in range(len(closes))]
    opens = closes[:1] + closes[:-1]
    return run_top_bottom_backtest("ADANIGREEN", "ADANIGREEN-EQ", "", "STOCK", 1, dates, closes, opens)


def test_mandatory_sequence_produces_exactly_three_alternating_trades():
    signals, trades = _run(MANDATORY_CLOSES)

    assert [t.direction for t in trades] == ["BUY", "SELL", "BUY"], (
        "structure points must not each create their own trade"
    )


def test_mandatory_sequence_buy_entry_uses_system_point_90_and_stop_85():
    _, trades = _run(MANDATORY_CLOSES)
    buy = trades[0]
    # 80=BOTTOM, 90=TOP, 85=NEW BOTTOM are structure. Only the close
    # crossing above 90 creates the BUY (the close that does it is 95) —
    # and the fill is AT the System Point 90, since that is where the
    # resting order sits, not at the close that swept through it.
    assert buy.system_point == 90
    assert buy.initial_sl == 85
    assert buy.entry_price == 90


def test_mandatory_sequence_buy_stop_trails_85_to_100_to_108():
    _, trades = _run(MANDATORY_CLOSES)
    buy = trades[0]
    assert [v for _, v in buy.stop_history] == [85, 100, 108]


def test_mandatory_sequence_buy_exits_and_reverses_to_sell_at_the_stop_level():
    _, trades = _run(MANDATORY_CLOSES)
    buy, sell = trades[0], trades[1]
    # The close that breaches is 107; the stop rests at 108, so both the
    # exit and the reversal entry fill at 108 — exit price and the next
    # entry price are the same level by construction.
    assert buy.exit_price == 108
    assert buy.exit_reason == "TRAILING_STOP_REVERSAL"
    assert sell.entry_price == 108
    assert sell.reversal_event_id == buy.reversal_event_id  # ONE reversal event


def test_mandatory_sequence_sell_stop_trails_downward_to_62():
    _, trades = _run(MANDATORY_CLOSES)
    sell = trades[1]
    stops = [v for _, v in sell.stop_history]
    assert stops == sorted(stops, reverse=True), "a SELL stop must never move back up"
    assert stops[-1] == 62
    assert sell.active_stop == 62


def test_mandatory_sequence_sell_exits_and_reverses_to_buy_at_the_stop_level():
    _, trades = _run(MANDATORY_CLOSES)
    sell, final_buy = trades[1], trades[2]
    # Breaching close is 63; the stop rests at 62, so both fill at 62.
    assert sell.exit_price == 62
    assert sell.exit_reason == "TRAILING_STOP_REVERSAL"
    assert final_buy.entry_price == 62
    assert final_buy.reversal_event_id == sell.reversal_event_id


def test_mandatory_sequence_has_no_duplicate_same_direction_entries():
    signals, trades = _run(MANDATORY_CLOSES)
    for a, b in zip(trades, trades[1:]):
        assert a.direction != b.direction
    # 17 structure points were confirmed in this series, but only 3 entries.
    assert len(signals) == 3


def test_tops_and_bottoms_alone_never_create_trades():
    # Pure oscillation that makes many Tops/Bottoms but never crosses the
    # System Point in a way that should open more than the first position.
    _, trades = _run([100, 80, 90, 85, 95])
    assert len(trades) == 1
    assert trades[0].direction == "BUY"
