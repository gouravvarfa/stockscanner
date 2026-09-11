import pandas as pd

from backend.config.expiry_level_5_config import ExpiryLevel5Config
from backend.strategies.expiry_level_5 import detect_expiry_level_5_signal


def _df(rows):
    idx = pd.bdate_range("2024-01-01", periods=len(rows))
    data = {"open": [], "high": [], "low": [], "close": [], "volume": []}
    for o, h, l, c in rows:
        data["open"].append(o)
        data["high"].append(h)
        data["low"].append(l)
        data["close"].append(c)
        data["volume"].append(1000)
    return pd.DataFrame(data, index=idx)


def _rally():
    # Swing low ~99 (day0), swing high ~202 (day10) -> fib 61.8% ~138.3
    return [(100 + 10 * i, 100 + 10 * i + 2, 100 + 10 * i - 1, 100 + 10 * i + 1) for i in range(11)]


def test_valid_support_and_confirmation_signals_buy_ce():
    touch = (141, 142, 138, 140)
    confirm = (141, 146, 139, 145)
    df = _df(_rally() + [touch, confirm])

    signal = detect_expiry_level_5_signal("RELIANCE", df, ExpiryLevel5Config())

    assert signal is not None
    assert signal.signal == "BUY_CE"
    assert signal.strategy == "EXPIRY_LEVEL_5"
    assert signal.support_confirmed
    assert signal.confirmation_close_above_previous_high


def test_touches_618_but_breaks_down_no_signal():
    touch = (141, 142, 138, 140)
    breakdown = (139, 140, 120, 122)  # closes well below the level -> decisive break
    confirm = (123, 146, 122, 145)  # even though this closes above breakdown's high, support already broken
    df = _df(_rally() + [touch, breakdown, confirm])

    signal = detect_expiry_level_5_signal("RELIANCE", df, ExpiryLevel5Config())
    assert signal is None


def test_stays_above_618_without_testing_it_no_signal():
    # Never dips down toward the 61.8% zone at all.
    stay_high = (195, 205, 190, 200)
    confirm = (200, 215, 199, 210)
    df = _df(_rally() + [stay_high, confirm])

    signal = detect_expiry_level_5_signal("RELIANCE", df, ExpiryLevel5Config())
    assert signal is None


def test_support_confirmed_but_no_close_above_previous_high_no_signal():
    touch = (141, 142, 138, 140)
    weak_candle = (140, 141, 139, 140.5)  # close does not exceed touch bar's high (142)
    df = _df(_rally() + [touch, weak_candle])

    signal = detect_expiry_level_5_signal("RELIANCE", df, ExpiryLevel5Config())
    assert signal is None


def test_close_exactly_at_previous_high_no_signal():
    touch = (141, 142, 138, 140)
    exact = (141, 142, 139, 142.0)  # close == previous bar's high, not strictly greater
    df = _df(_rally() + [touch, exact])

    signal = detect_expiry_level_5_signal("RELIANCE", df, ExpiryLevel5Config())
    assert signal is None


def test_incomplete_candle_excluded_by_caller_yields_no_premature_signal():
    # Simulates the caller correctly NOT including the still-forming candle:
    # only the touch bar is present, no confirmation bar yet -> no signal.
    touch = (141, 142, 138, 140)
    df = _df(_rally() + [touch])

    signal = detect_expiry_level_5_signal("RELIANCE", df, ExpiryLevel5Config())
    assert signal is None


def test_signal_fires_once_not_on_every_subsequent_candle():
    touch = (141, 142, 138, 140)
    # low raised to 165 — clear of the WIDENED 38.2%-61.8% zone (~[137, 164]
    # with tolerance) — so this confirmation bar itself can't be mistaken
    # for a fresh touch later.
    confirm = (165, 170, 165, 168)
    later_candle = (168, 172, 167, 170)  # setup already confirmed; this is just a later, unrelated bar

    df_at_confirm = _df(_rally() + [touch, confirm])
    df_later = _df(_rally() + [touch, confirm, later_candle])

    first = detect_expiry_level_5_signal("RELIANCE", df_at_confirm, ExpiryLevel5Config())
    second = detect_expiry_level_5_signal("RELIANCE", df_later, ExpiryLevel5Config())

    assert first is not None
    assert second is None  # no repeat signal on the next candle


def test_new_touch_after_previous_setup_allows_new_signal():
    first_touch = (141, 142, 138, 140)
    first_confirm = (141, 146, 139, 145)
    pullback_again = (144, 145, 139, 141)  # dips back toward 61.8% again
    second_touch = (140, 141, 138, 139)
    second_confirm = (139, 150, 138, 148)

    df = _df(_rally() + [first_touch, first_confirm, pullback_again, second_touch, second_confirm])

    signal = detect_expiry_level_5_signal("RELIANCE", df, ExpiryLevel5Config())
    assert signal is not None
    # The fresh signal is anchored to the SECOND touch, not the first.
    assert signal.support_price == 138.0


def test_touch_anywhere_in_38_to_61_zone_counts_as_support():
    # Swing low ~99, swing high ~202 -> fib 38.2% ~162.65, fib 61.8% ~138.35.
    # A touch near the SHALLOW (38.2%) edge, not the deep 61.8% point, must
    # still count as valid support now that the whole zone is accepted.
    shallow_touch = (163, 164, 161, 162)
    confirm = (163, 168, 162, 167)
    df = _df(_rally() + [shallow_touch, confirm])

    signal = detect_expiry_level_5_signal("RELIANCE", df, ExpiryLevel5Config())

    assert signal is not None
    assert signal.support_price == 161.0


def test_touch_below_the_zone_still_rejected():
    # A close well below the 61.8% deep edge (with tolerance) is a decisive
    # break of the zone, not a touch within it -> must not count as support.
    deep_break = (110, 112, 105, 108)
    confirm = (108, 130, 107, 128)
    df = _df(_rally() + [deep_break, confirm])

    signal = detect_expiry_level_5_signal("RELIANCE", df, ExpiryLevel5Config())
    assert signal is None


def test_insufficient_data_no_signal():
    df = _df(_rally()[:2])
    signal = detect_expiry_level_5_signal("RELIANCE", df, ExpiryLevel5Config())
    assert signal is None
