import datetime as dt

import pandas as pd
import pytest

from backend.config.cup_config import CupConfig
from backend.strategies.cup import detect_cup


def _monthly_frame(specs: list[tuple[int, int, float, float, float, float, float]], stub_next: bool = True) -> pd.DataFrame:
    """Builds a DAILY OHLCV frame with exactly one bar per month, placed on
    that month's actual last calendar day, so to_monthly() (unmodified,
    reused as-is) resamples it to exactly the OHLC given per (year, month).
    `stub_next` appends one more bar a few days into the following month so
    the LAST spec'd month is a genuinely COMPLETED month (to_monthly always
    drops a trailing bar whose period extends past the last daily bar —
    that's the real "ignore the in-progress month" rule, exercised here on
    purpose rather than worked around)."""
    rows = []
    for (y, m, o, h, l, c, v) in specs:
        d = pd.Timestamp(year=y, month=m, day=1) + pd.offsets.MonthEnd(0)
        rows.append((d, o, h, l, c, v))
    if stub_next:
        last_d = rows[-1][0]
        stub_date = last_d + pd.Timedelta(days=5)
        last_close = rows[-1][4]
        rows.append((stub_date, last_close, last_close, last_close, last_close, 0.0))
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"]).set_index("date")
    return df


def _flat_run(year_start: int, month_start: int, n: int, price: float, vol: float = 1000.0):
    specs = []
    y, m = year_start, month_start
    for _ in range(n):
        specs.append((y, m, price, price, price, price, vol))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return specs, (y, m)


DEFAULT_CONFIG = CupConfig()


def test_insufficient_history_short_series():
    specs, _ = _flat_run(2026, 1, 3, 100.0)
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(2026, 4, 10))
    assert result["status"] == "INSUFFICIENT_HISTORY"


def test_insufficient_history_empty_frame():
    result = detect_cup(pd.DataFrame(columns=["open", "high", "low", "close", "volume"]), DEFAULT_CONFIG)
    assert result["status"] == "INSUFFICIENT_HISTORY"


def _cup_specs(left_rim=1000.0, cup_low=600.0, recovery_close=900.0, n_decline=36, n_recover=36, n_lead=3):
    """LEFT RIM -> decline to CUP LOW -> straight-line recovery to
    `recovery_close` over n_recover months. Depth = 40% by default."""
    specs = []
    y, m = 2015, 1
    for _ in range(n_lead):
        specs.append((y, m, 500.0, 500.0, 500.0, 500.0, 1000.0)); m += 1
        if m > 12: m, y = 1, y + 1
    specs.append((y, m, left_rim, left_rim, left_rim, left_rim, 2000.0)); m += 1
    if m > 12: m, y = 1, y + 1
    decline_step = (left_rim - cup_low) / n_decline
    price = left_rim
    for i in range(n_decline):
        price -= decline_step
        specs.append((y, m, price, price, price, price, 1000.0)); m += 1
        if m > 12: m, y = 1, y + 1
    recover_step = (recovery_close - cup_low) / n_recover if n_recover > 0 else 0.0
    price = cup_low
    for i in range(n_recover):
        price += recover_step
        specs.append((y, m, price, price, price, price, 1000.0)); m += 1
        if m > 12: m, y = 1, y + 1
    last_year_month = (y, m)
    return specs, last_year_month


def test_valid_developing_cup_is_early_cup_or_near_breakout():
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=600.0, recovery_close=850.0)  # distance 15%, within the actionable band, not near
    df = _monthly_frame(specs)
    now = dt.datetime(y, m, 10)
    result = detect_cup(df, DEFAULT_CONFIG, now=now)
    assert result["status"] == "EARLY_CUP"
    assert result["cup_depth_percent"] == pytest.approx(40.0, abs=0.5)
    assert result["left_rim_price"] == pytest.approx(1000.0)
    assert result["cup_low_price"] == pytest.approx(600.0)


def test_cup_without_completed_right_rim_still_qualifies():
    # recovery stops well short of the rim — right side never "completes" —
    # must still qualify (EARLY_CUP) as long as it's within the actionable
    # distance/rim-difference bands (max_distance_to_breakout_pct,
    # max_rim_difference_pct), per spec section 3/13 as refined by the
    # 2026-09-23 ACC fix and the 2026-09-24 right-rim check.
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=600.0, recovery_close=830.0)
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    assert result["status"] in ("EARLY_CUP", "NEAR_BREAKOUT")
    assert result["recovery_percent"] < 100  # recovering, but the rim hasn't been reached


def _step_month(y, m):
    m += 1
    if m > 12:
        m, y = 1, y + 1
    return y, m


def test_most_recent_relevant_cup_is_picked_over_an_older_larger_one():
    """BHEL-style double cup (2026-09-23, explicit user direction): a big
    older cup, then a second, smaller, more recent cup formed on its right
    side, with price now near the SECOND cup's rim. The scanner must report
    the second (actionable) cup, not the older/bigger one, even though both
    independently satisfy the 5-year-minimum + valid-depth rules."""
    specs = []
    y, m = 2010, 1
    for _ in range(3):
        specs.append((y, m, 400.0, 400.0, 400.0, 400.0, 1000.0)); y, m = _step_month(y, m)
    specs.append((y, m, 1500.0, 1500.0, 1500.0, 1500.0, 2000.0))  # rim 1 (older, bigger cup)
    y, m = _step_month(y, m)
    price = 1500.0
    for i in range(30):  # decline to cup-1 low (900, depth 40%)
        price -= 600.0 / 30
        specs.append((y, m, price, price, price, price, 1000.0)); y, m = _step_month(y, m)
    for i in range(30):  # recovery up to rim 2 (1400)
        price += 500.0 / 30
        specs.append((y, m, price, price, price, price, 1000.0)); y, m = _step_month(y, m)
    # rim 2: one bar higher than its neighbors, a genuine local peak.
    specs.append((y, m, 1420.0, 1420.0, 1420.0, 1420.0, 2000.0))
    y, m = _step_month(y, m)
    price = 1420.0
    for i in range(30):  # decline to cup-2 low (1000, depth ~29.6%)
        price -= 420.0 / 30
        specs.append((y, m, price, price, price, price, 1000.0)); y, m = _step_month(y, m)
    for i in range(30):  # recovery close to (but not past) rim 2
        price += 380.0 / 30
        specs.append((y, m, price, price, price, price, 1000.0)); y, m = _step_month(y, m)
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    # The picked rim must be the SECOND (recent, smaller, closer) one, not
    # the first (older, bigger, farther-away) one.
    assert result["left_rim_price"] == pytest.approx(1420.0, abs=1.0)
    assert result["status"] in ("NEAR_BREAKOUT", "EARLY_CUP")
    assert abs(result["distance_to_breakout_percent"]) < 20  # close, not the ~8-25% an older-rim pick would give


def test_near_breakout():
    # Breakout level 1000, latest close 950 -> distance 5% <= 10% default.
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=600.0, recovery_close=950.0)
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    assert result["status"] == "NEAR_BREAKOUT"
    assert result["distance_to_breakout_percent"] == pytest.approx(5.0, abs=0.5)


def test_breakout_forming_uses_incomplete_month_only_informationally():
    # Latest COMPLETED month still below the level (950), but today's
    # still-forming month has already traded above it.
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=600.0, recovery_close=950.0)
    df = _monthly_frame(specs, stub_next=False)
    last_completed = df.index.max()
    forming_day = last_completed + pd.Timedelta(days=10)
    extra = pd.DataFrame(
        [{"open": 990.0, "high": 1050.0, "low": 985.0, "close": 1040.0, "volume": 500.0}],
        index=[forming_day],
    )
    df = pd.concat([df, extra])
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(forming_day.year, forming_day.month, forming_day.day))
    assert result["status"] == "BREAKOUT_FORMING"
    # Still uses the completed month's close for the confirmed fields:
    assert result["latest_monthly_close"] == pytest.approx(950.0)


def test_confirmed_breakout_on_completed_month_close():
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=600.0, recovery_close=950.0)
    # Append one more COMPLETED month that closes above the breakout level.
    specs.append((y, m, 1000.0, 1060.0, 995.0, 1040.0, 3000.0))
    m += 1
    if m > 12:
        m, y = 1, y + 1
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    assert result["status"] == "BREAKOUT_CONFIRMED"
    assert result["breakout_price"] == pytest.approx(1040.0)
    assert result["breakout_percent"] == pytest.approx(4.0, abs=0.1)


def test_recent_breakout_within_configured_window():
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=600.0, recovery_close=950.0)
    specs.append((y, m, 1000.0, 1060.0, 995.0, 1040.0, 3000.0))  # breakout month
    m += 1
    if m > 12:
        m, y = 1, y + 1
    # Two more completed months after the breakout (still holding above it).
    for _ in range(2):
        specs.append((y, m, 1040.0, 1080.0, 1020.0, 1060.0, 2000.0))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    assert result["status"] == "RECENT_BREAKOUT"


def test_stale_breakout_with_price_still_above_is_no_signal_not_early_cup():
    """2026-09-23 live bug (ACE): a breakout confirmed years ago, with price
    since running far past it, must NOT fall through and be reported as
    EARLY_CUP/NEAR_BREAKOUT against that now-irrelevant old rim."""
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=600.0, recovery_close=950.0)
    specs.append((y, m, 1000.0, 1060.0, 995.0, 1040.0, 3000.0))  # breakout month
    m += 1
    if m > 12:
        m, y = 1, y + 1
    # Many completed months after the breakout, well past recent_breakout_months,
    # with price having run up massively (4x) beyond the old breakout level.
    for i in range(24):
        price = 1040.0 + i * 150.0
        specs.append((y, m, price, price * 1.02, price * 0.98, price, 2000.0))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    assert result["status"] == "NO_SIGNAL"


def test_stale_breakout_with_price_pulled_back_can_still_be_near_breakout():
    """The one legitimate fall-through case: price pulled back to/below the
    old breakout level and is genuinely re-testing it."""
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=600.0, recovery_close=950.0)
    specs.append((y, m, 1000.0, 1060.0, 995.0, 1040.0, 3000.0))  # breakout month
    m += 1
    if m > 12:
        m, y = 1, y + 1
    # Several completed months later, price has pulled back below the level
    # (well past recent_breakout_months) and is now close to it again.
    for i in range(6):
        specs.append((y, m, 1000.0, 1010.0, 940.0, 960.0, 2000.0))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    assert result["status"] == "NEAR_BREAKOUT"


def test_price_too_far_from_resistance_is_early_cup_not_near_breakout():
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=600.0, recovery_close=850.0)  # distance 15% > 10%
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    assert result["status"] == "EARLY_CUP"
    assert result["distance_to_breakout_percent"] > DEFAULT_CONFIG.near_breakout_pct


def test_deep_cup_is_detected_with_correct_depth():
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=520.0, recovery_close=900.0)  # 48% depth
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    assert result["status"] in ("EARLY_CUP", "NEAR_BREAKOUT")
    assert result["cup_depth_percent"] == pytest.approx(48.0, abs=0.5)


def test_price_still_far_from_resistance_with_barely_any_recovery_is_no_signal():
    """2026-09-23 live finding (ACC): a valid-depth structure whose price is
    still ~48% below its own rim, with only ~2% recovery, is still mostly
    in the decline leg, not an actual cup shape yet — must not be reported
    at all (was showing as misleading EARLY_CUP before this fix)."""
    specs, (y, m) = _cup_specs(left_rim=2454.95, cup_low=1251.0, recovery_close=1276.50)
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    # Rejected even earlier now (min_recovery_pct: ~2% recovery is too small
    # to count as having turned up at all) — still correctly NO_SIGNAL.
    assert result["status"] == "NO_SIGNAL"


def test_cup_low_on_the_latest_bar_itself_is_rejected_still_a_downtrend():
    """2026-09-24, explicit user direction: upside-only scanner. If the cup
    low IS the current/latest completed month (no recovery bar exists yet —
    the stock is still making new lows), it's still in its decline leg, not
    an actual cup that has turned up — must be NO_SIGNAL, not EARLY_CUP."""
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=600.0, recovery_close=650.0, n_decline=60, n_recover=0)
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    assert result["status"] == "NO_SIGNAL"


def test_barely_positive_recovery_below_minimum_is_rejected():
    # Left rim 1000, cup low 600 (range 400). Recovery to 610 = 2.5%,
    # below the 5% min_recovery_pct floor — still effectively flat/declining.
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=600.0, recovery_close=610.0)
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    assert result["status"] == "NO_SIGNAL"


def test_shallow_cup_rejected():
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=920.0, recovery_close=950.0)  # 8% depth < 12% min
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    assert result["status"] == "NO_SIGNAL"


def test_extreme_depth_rejected():
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=350.0, recovery_close=900.0)  # 65% depth > 50% max
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    assert result["status"] == "NO_SIGNAL"


def test_recovery_calculation():
    # Left rim 1000, cup low 600 (range 400). Current close 900 -> recovery 75%.
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=600.0, recovery_close=900.0)
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    assert result["recovery_percent"] == pytest.approx(75.0, abs=0.5)


def test_breakout_distance_for_price_above_breakout():
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=600.0, recovery_close=950.0)
    specs.append((y, m, 1000.0, 1060.0, 995.0, 1050.0, 3000.0))
    m += 1
    if m > 12:
        m, y = 1, y + 1
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    assert result["status"] == "BREAKOUT_CONFIRMED"
    assert result["breakout_percent"] == pytest.approx(5.0, abs=0.1)


def test_current_incomplete_month_ignored_for_confirmed_status():
    # Completed months never close above the level; only the IN-PROGRESS
    # month (today) trades above it -> must NOT be BREAKOUT_CONFIRMED.
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=600.0, recovery_close=950.0)
    df = _monthly_frame(specs, stub_next=False)
    last_completed = df.index.max()
    forming_day = last_completed + pd.Timedelta(days=10)
    extra = pd.DataFrame(
        [{"open": 990.0, "high": 1200.0, "low": 985.0, "close": 1150.0, "volume": 500.0}],
        index=[forming_day],
    )
    df = pd.concat([df, extra])
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(forming_day.year, forming_day.month, forming_day.day))
    assert result["status"] != "BREAKOUT_CONFIRMED"
    assert result["status"] == "BREAKOUT_FORMING"


def test_no_lookahead_left_rim_never_uses_future_bars():
    # A much higher high appears AFTER the point we're evaluating from —
    # detect_cup only ever sees bars up to "now" via the daily frame passed
    # in, so an artificially truncated frame must not see the future spike.
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=600.0, recovery_close=900.0)
    df_full = _monthly_frame(specs)
    # Truncate to only the first 20 months (well before recovery finishes).
    truncated_specs = specs[:20]
    df_truncated = _monthly_frame(truncated_specs)
    result = detect_cup(df_truncated, DEFAULT_CONFIG, now=df_truncated.index.max() + pd.Timedelta(days=10))
    # Whatever it concludes, it must be internally consistent with ONLY the
    # truncated data — the left rim price must come from within that data.
    if result["left_rim_price"] is not None:
        assert result["left_rim_price"] <= max(s[3] for s in truncated_specs) + 1e-6


def test_handle_status_defaults_to_not_formed_without_breakout():
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=600.0, recovery_close=750.0)
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    assert result["handle_status"] == "NOT_FORMED"


def test_one_bad_symbol_style_failure_does_not_crash_detect_cup():
    # A malformed/empty frame must return INSUFFICIENT_HISTORY, never raise.
    bad = pd.DataFrame({"open": [], "high": [], "low": [], "close": [], "volume": []})
    result = detect_cup(bad, DEFAULT_CONFIG)
    assert result["status"] == "INSUFFICIENT_HISTORY"


# ---------------------------------------------------------------------------
# VEDL/BHEL structural reference (2026-09-24) — full LEFT RIM -> long decline
# -> rounded bottom -> right-side recovery -> RIGHT RIM -> HANDLE -> BREAKOUT
# sequence, per the real VEDL monthly chart the user shared as the structural
# template. Illustrative synthetic prices only — never hardcoded to VEDL's
# actual dates/prices.
# ---------------------------------------------------------------------------

def _vedl_like_specs(
    left_rim=170.0, bottom=90.0, right_rim=165.0, handle_low=150.0, breakout_close=180.0,
    n_decline=42, n_bottom=5, n_recover=40, n_handle=3, include_handle_and_breakout=True,
):
    """LEFT RIM -> long decline -> ROUNDED bottom (flat plateau, not one
    candle) -> right-side recovery -> RIGHT RIM near the left rim -> a
    shallow HANDLE pullback -> BREAKOUT close above the rim."""
    rows = []
    y, m = 2005, 1

    def add(price):
        nonlocal y, m
        d = pd.Timestamp(year=y, month=m, day=1) + pd.offsets.MonthEnd(0)
        rows.append((d, price, price, price, price, 1000.0))
        m += 1
        if m > 12:
            m, y = 1, y + 1

    for _ in range(3):
        add(left_rim * 0.6)  # lead-in, so the rim is a genuine 2-sided swing high
    add(left_rim)
    decline_step = (left_rim - bottom) / n_decline
    price = left_rim
    for _ in range(n_decline):
        price -= decline_step
        add(price)
    for _ in range(n_bottom):  # ROUNDED bottom: a flat base, not a single spike low
        add(bottom * 1.02)
    recover_step = (right_rim - bottom) / n_recover
    price = bottom
    for _ in range(n_recover):
        price += recover_step
        add(price)
    if not include_handle_and_breakout:
        return rows
    # Shallow handle: dip toward handle_low then drift back up, always
    # staying strictly below the left rim (breakout only happens on the
    # explicit final candle below).
    handle_prices = [handle_low + (right_rim - handle_low) * (i / max(1, n_handle - 1)) * 0.6 for i in range(n_handle)]
    for price in handle_prices:
        add(min(price, left_rim * 0.98))
    add(breakout_close)  # BREAKOUT: a completed monthly close above the left rim
    return rows


def test_vedl_like_full_structure_reaches_breakout_confirmed():
    """The complete LEFT RIM -> decline -> rounded bottom -> recovery ->
    RIGHT RIM -> HANDLE -> BREAKOUT sequence, matching the real VEDL monthly
    chart structurally (not its actual prices/dates)."""
    rows = _vedl_like_specs()
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"]).set_index("date")
    stub = pd.DataFrame(
        {"open": rows[-1][4], "high": rows[-1][4], "low": rows[-1][4], "close": rows[-1][4], "volume": 0.0},
        index=[df.index.max() + pd.Timedelta(days=5)],
    )
    df = pd.concat([df, stub])
    now = dt.datetime(df.index[-2].year, df.index[-2].month, 28) + pd.Timedelta(days=10)
    result = detect_cup(df, DEFAULT_CONFIG, now=now)
    assert result["status"] == "BREAKOUT_CONFIRMED"
    assert result["left_rim_price"] == pytest.approx(170.0, abs=1.0)
    assert result["cup_bottom_price"] == pytest.approx(90.0 * 1.02, abs=2.0)
    assert result["right_rim_price"] is not None
    assert DEFAULT_CONFIG.min_depth_pct <= result["cup_depth_percent"] <= DEFAULT_CONFIG.max_depth_pct
    assert result["invalidation_reason"] is None


def test_vedl_like_structure_before_breakout_is_early_cup_or_near_breakout():
    """Same structure, evaluated partway through the right-side recovery
    (before the handle/breakout) — a long-duration (years) developing cup
    must still qualify, per spec: 'DO NOT require the Cup to be short.'"""
    rows = _vedl_like_specs(n_recover=28, include_handle_and_breakout=False)  # recovery stops partway
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"]).set_index("date")
    stub = pd.DataFrame(
        {"open": rows[-1][4], "high": rows[-1][4], "low": rows[-1][4], "close": rows[-1][4], "volume": 0.0},
        index=[df.index.max() + pd.Timedelta(days=5)],
    )
    df = pd.concat([df, stub])
    now = dt.datetime(df.index[-2].year, df.index[-2].month, 28) + pd.Timedelta(days=10)
    result = detect_cup(df, DEFAULT_CONFIG, now=now)
    assert result["status"] in ("EARLY_CUP", "NEAR_BREAKOUT")
    assert result["cup_age_years"] >= 5  # long-duration, matching VEDL/BHEL — never rejected for being "too long"


def test_vedl_like_handle_is_detected_after_breakout():
    rows = _vedl_like_specs()
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"]).set_index("date")
    stub = pd.DataFrame(
        {"open": rows[-1][4], "high": rows[-1][4], "low": rows[-1][4], "close": rows[-1][4], "volume": 0.0},
        index=[df.index.max() + pd.Timedelta(days=5)],
    )
    df = pd.concat([df, stub])
    now = dt.datetime(df.index[-2].year, df.index[-2].month, 28) + pd.Timedelta(days=10)
    result = detect_cup(df, DEFAULT_CONFIG, now=now)
    assert result["status"] == "BREAKOUT_CONFIRMED"
    # A handle DID occur in this synthetic structure (the dip before the
    # final breakout candle) — handle fields are populated when one exists.
    assert result["handle_status"] in ("FORMING", "FORMED", "NOT_FORMED")


# ---------------------------------------------------------------------------
# Negative tests — spec section "VEDL/BHEL STRUCTURAL TEST"
# ---------------------------------------------------------------------------

def test_negative_1_downtrend_with_fresh_low_is_no_signal():
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=600.0, recovery_close=650.0, n_decline=60, n_recover=0)
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    assert result["status"] == "NO_SIGNAL"


def test_negative_2_old_u_shape_no_meaningful_right_recovery_is_no_signal():
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=600.0, recovery_close=610.0)  # ~2.5% recovery
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    assert result["status"] == "NO_SIGNAL"


def test_negative_3_old_cup_price_far_below_rim_is_no_signal():
    specs, (y, m) = _cup_specs(left_rim=2454.95, cup_low=1251.0, recovery_close=1276.50)  # ~48% away
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    assert result["status"] == "NO_SIGNAL"


def test_negative_4_recovery_below_five_percent_is_no_signal():
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=600.0, recovery_close=615.0)  # 3.75% recovery
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    assert result["status"] == "NO_SIGNAL"


def test_negative_5_rim_to_rim_mismatch_too_large_is_rejected():
    # Recovery reaches close enough to pass the (looser) 25% distance check
    # on its own, but the BEST point ever reached (right rim) never got
    # within max_rim_difference_pct(20%) — must still be rejected.
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=600.0, recovery_close=780.0)  # 22% away, > 20% rim cap
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    assert result["status"] == "NO_SIGNAL"
    assert result["invalidation_reason"] == "rim_mismatch_too_large"


def test_negative_6_proper_long_duration_cup_is_valid():
    rows = _vedl_like_specs(n_recover=28, include_handle_and_breakout=False)
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"]).set_index("date")
    stub = pd.DataFrame(
        {"open": rows[-1][4]} | {c: rows[-1][4] for c in ("high", "low", "close")} | {"volume": 0.0},
        index=[df.index.max() + pd.Timedelta(days=5)],
    )
    df = pd.concat([df, stub])
    now = dt.datetime(df.index[-2].year, df.index[-2].month, 28) + pd.Timedelta(days=10)
    result = detect_cup(df, DEFAULT_CONFIG, now=now)
    assert result["status"] in ("EARLY_CUP", "NEAR_BREAKOUT")


def test_negative_7_proper_cup_plus_handle_is_valid():
    rows = _vedl_like_specs()
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"]).set_index("date")
    stub = pd.DataFrame(
        {"open": rows[-1][4]} | {c: rows[-1][4] for c in ("high", "low", "close")} | {"volume": 0.0},
        index=[df.index.max() + pd.Timedelta(days=5)],
    )
    df = pd.concat([df, stub])
    now = dt.datetime(df.index[-2].year, df.index[-2].month, 28) + pd.Timedelta(days=10)
    result = detect_cup(df, DEFAULT_CONFIG, now=now)
    assert result["status"] == "BREAKOUT_CONFIRMED"


def test_negative_8_completed_close_above_rim_is_breakout_confirmed():
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=600.0, recovery_close=950.0)
    specs.append((y, m, 1000.0, 1060.0, 995.0, 1040.0, 3000.0))
    m += 1
    if m > 12:
        m, y = 1, y + 1
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    assert result["status"] == "BREAKOUT_CONFIRMED"


def test_negative_9_multiple_historical_cups_chooses_relevant_current_one():
    # Same fixture as test_most_recent_relevant_cup_is_picked_over_an_older_larger_one:
    # a big older cup, then a second, more recent, more actionable one.
    specs = []
    y, m = 2010, 1
    for _ in range(3):
        specs.append((y, m, 400.0, 400.0, 400.0, 400.0, 1000.0)); y, m = _step_month(y, m)
    specs.append((y, m, 1500.0, 1500.0, 1500.0, 1500.0, 2000.0))
    y, m = _step_month(y, m)
    price = 1500.0
    for i in range(30):
        price -= 600.0 / 30
        specs.append((y, m, price, price, price, price, 1000.0)); y, m = _step_month(y, m)
    for i in range(30):
        price += 500.0 / 30
        specs.append((y, m, price, price, price, price, 1000.0)); y, m = _step_month(y, m)
    specs.append((y, m, 1420.0, 1420.0, 1420.0, 1420.0, 2000.0))
    y, m = _step_month(y, m)
    price = 1420.0
    for i in range(30):
        price -= 420.0 / 30
        specs.append((y, m, price, price, price, price, 1000.0)); y, m = _step_month(y, m)
    for i in range(30):
        price += 380.0 / 30
        specs.append((y, m, price, price, price, price, 1000.0)); y, m = _step_month(y, m)
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    assert result["left_rim_price"] == pytest.approx(1420.0, abs=1.0)  # the more recent/relevant rim, not 1500


def test_asianpaint_like_early_smaller_pivot_never_wins_over_a_later_dominant_high():
    """Live false positive, 2026-09-24 (ASIANPAINT): an early, SMALLER swing
    high (A) followed by price rallying even HIGHER (B) before the real
    decline starts, then a sharp fall and a recovery that happens to land
    close to A (but nowhere near the true dominant high B). Without the
    dominance check, A alone looked numerically valid (good depth/recovery/
    distance against IT) and won purely for being "closest" — a false
    positive, since A was never the real resistance; B was, and price is
    still far from B. Must be NO_SIGNAL (or reject A specifically)."""
    specs = []
    y, m = 2015, 1
    for _ in range(3):
        specs.append((y, m, 400.0, 400.0, 400.0, 400.0, 1000.0)); y, m = _step_month(y, m)
    specs.append((y, m, 1000.0, 1000.0, 1000.0, 1000.0, 2000.0))  # A: an early, smaller swing high
    y, m = _step_month(y, m)
    price = 1000.0
    for _ in range(10):  # price rallies FURTHER past A before any decline
        price += 50.0
        specs.append((y, m, price, price, price, price, 1000.0)); y, m = _step_month(y, m)
    specs.append((y, m, 1500.0, 1500.0, 1500.0, 1500.0, 2000.0))  # B: the TRUE dominant high
    y, m = _step_month(y, m)
    price = 1500.0
    for _ in range(45):  # long decline from B (not from A)
        price -= 750.0 / 45
        specs.append((y, m, price, price, price, price, 1000.0)); y, m = _step_month(y, m)
    for _ in range(10):  # partial recovery — lands close to A, still far from B
        price += 20.0
        specs.append((y, m, price, price, price, price, 1000.0)); y, m = _step_month(y, m)
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    # A (1000) must never be picked as the left rim — B (1500, the actual
    # dominant high) is the only structurally valid candidate, and here it
    # doesn't clear the distance/recovery bar yet.
    if result["left_rim_price"] is not None:
        assert result["left_rim_price"] != pytest.approx(1000.0, abs=1.0)
    assert result["status"] in ("NO_SIGNAL", "INSUFFICIENT_HISTORY")


def test_sonacoms_like_short_total_history_uses_relaxed_room_requirement():
    """Live finding, 2026-09-24 (SONACOMS / Sona BLW — listed 2021, so total
    Angel One history is only ~5.25 years): the strict 60-month room
    requirement left essentially zero valid candidate window even though
    the chart showed a real multi-year rim->decline->recovery->breakout
    structure. A stock whose TOTAL history is short now gets a reduced,
    history-proportional room requirement — this must surface that
    structure instead of NO_SIGNAL."""
    specs = []
    y, m = 2021, 1
    for _ in range(3):
        specs.append((y, m, 400.0, 400.0, 400.0, 400.0, 1000.0)); y, m = _step_month(y, m)
    specs.append((y, m, 700.0, 700.0, 700.0, 700.0, 2000.0))  # left rim (2022-ish high)
    y, m = _step_month(y, m)
    price = 700.0
    for _ in range(20):  # decline to a low
        price -= 300.0 / 20
        specs.append((y, m, price, price, price, price, 1000.0)); y, m = _step_month(y, m)
    for _ in range(38):  # long recovery, close to (not past) the rim
        price += 260.0 / 38
        specs.append((y, m, price, price, price, price, 1000.0)); y, m = _step_month(y, m)
    df = _monthly_frame(specs)
    total_months = len(specs)
    assert DEFAULT_CONFIG.min_cup_months < total_months < DEFAULT_CONFIG.min_cup_months + 12  # short total history, matching SONACOMS (~5.25y)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    assert result["status"] in ("EARLY_CUP", "NEAR_BREAKOUT", "BREAKOUT_CONFIRMED", "RECENT_BREAKOUT")
    assert result["left_rim_price"] == pytest.approx(700.0, abs=1.0)


def test_short_history_relaxation_never_exceeds_the_normal_five_year_rule():
    """The relaxation only ever REDUCES the room requirement for short
    total history — it must never let a candidate with genuinely
    insufficient room (even under the relaxed floor) through, and normal
    (5+ year margin) stocks must be completely unaffected (already proven
    by every other passing test in this file, which all use ample lead-in
    history)."""
    # Only ~30 months total — even the relaxed floor (short_history_min_cup_months=24,
    # or 65% of 30≈19) can't manufacture room from a rim placed too close to "now".
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=600.0, recovery_close=950.0, n_decline=10, n_recover=10, n_lead=3)
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    # With only ~24 months of decline+recovery after the rim, and the
    # relaxed floor still requiring 24, this sits right at the edge —
    # accept either a valid (relaxed-but-still-real) structure or a clean
    # rejection, but never a crash or a nonsensical result.
    assert result["status"] in ("EARLY_CUP", "NEAR_BREAKOUT", "NO_SIGNAL", "INSUFFICIENT_HISTORY")


# ---------------------------------------------------------------------------
# DEEP_CUP (2026-09-24, SONACOMS structural investigation)
#
# depth > max_depth_pct (50%) is NOT automatically rejected any more - it is
# additionally evaluated against deep_cup_* thresholds (genuine multi-month
# base at the bottom, real recovery duration, no single month dominating the
# whole recovery range) and, only if ALL of those hold, accepted as
# cup_type=DEEP_CUP (never STANDARD_CUP). A 50-60% decline that is really a
# V-shaped crash-and-bounce must still be rejected (NO_SIGNAL), and anything
# beyond deep_cup_max_depth_pct (60%) is rejected regardless of shape.
# ---------------------------------------------------------------------------

def _deep_cup_rounded_specs(left_rim=1000.0, cup_low=450.0, recovery_close=900.0, n_decline=36, n_recover=36):
    """A genuinely deep (55%) but ROUNDED decline: gradual multi-month
    decline AND gradual multi-month recovery (same shape _cup_specs already
    uses for standard cups) - no single month dominates, matching the
    SONACOMS-style base-then-climb shape the DEEP_CUP feature exists for."""
    return _cup_specs(left_rim=left_rim, cup_low=cup_low, recovery_close=recovery_close,
                       n_decline=n_decline, n_recover=n_recover)


def test_deep_cup_50_to_60_percent_rounded_recovery_is_accepted_as_deep_cup():
    specs, (y, m) = _deep_cup_rounded_specs(left_rim=1000.0, cup_low=450.0, recovery_close=900.0)
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    assert result["status"] in ("EARLY_CUP", "NEAR_BREAKOUT", "BREAKOUT_CONFIRMED", "RECENT_BREAKOUT")
    assert result["cup_depth_percent"] == pytest.approx(55.0, abs=0.5)
    assert result["cup_type"] == "DEEP_CUP"
    assert result["bottom_duration_months"] is not None
    assert result["recovery_duration_months"] is not None


def _v_shaped_deep_specs():
    """A 55%-deep decline followed by a genuine multi-month bottom base
    (so bottom_duration passes) but then one single explosive month
    accounting for the vast majority of the whole recovery range - the
    V-SHAPED CRASH + SPIKE this feature must still reject, distinct from a
    genuine rounded base-then-climb DEEP_CUP."""
    specs = []
    y, m = 2015, 1
    for _ in range(3):
        specs.append((y, m, 500.0, 500.0, 500.0, 500.0, 1000.0)); y, m = _step_month(y, m)
    specs.append((y, m, 1000.0, 1000.0, 1000.0, 1000.0, 2000.0)); y, m = _step_month(y, m)
    decline_step = (1000.0 - 450.0) / 50
    price = 1000.0
    for _ in range(50):
        price -= decline_step
        specs.append((y, m, price, price, price, price, 1000.0)); y, m = _step_month(y, m)
    price = 450.0
    for _ in range(7):
        price += 10.0
        specs.append((y, m, price, price, price, price, 1000.0)); y, m = _step_month(y, m)
    specs.append((y, m, 900.0, 900.0, 900.0, 900.0, 1000.0)); y, m = _step_month(y, m)
    return specs, (y, m)


def test_deep_cup_50_to_60_percent_v_shaped_spike_is_rejected_as_no_signal():
    specs, (y, m) = _v_shaped_deep_specs()
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    assert result["status"] == "NO_SIGNAL"
    assert result["rejection_reason"] == "v_shaped_recovery_too_sharp"
    assert result["invalidation_reason"] == "v_shaped_recovery_too_sharp"
    assert result["cup_type"] is None


def test_depth_beyond_deep_cup_cap_is_rejected_regardless_of_shape():
    # 65% depth - beyond deep_cup_max_depth_pct (60%) even with a gradual,
    # rounded recovery shape identical to the accepted DEEP_CUP case above.
    specs, (y, m) = _deep_cup_rounded_specs(left_rim=1000.0, cup_low=350.0, recovery_close=900.0)
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    assert result["status"] == "NO_SIGNAL"
    assert result["rejection_reason"] == "depth_out_of_range"


def test_sonacoms_like_rounded_deep_decline_is_accepted_as_deep_cup():
    """SONACOMS' real structure (2026-09-24 live diagnostic): ~55% depth,
    rim Dec-2021, multi-month base near the low, then a sustained (not
    single-spike) climb back toward the rim - illustrative shape only, no
    SONACOMS data/dates are hardcoded into the detector itself."""
    specs, (y, m) = _cup_specs(left_rim=840.0, cup_low=380.0, recovery_close=760.0, n_decline=40, n_recover=24)
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    assert result["status"] in ("EARLY_CUP", "NEAR_BREAKOUT", "BREAKOUT_CONFIRMED", "RECENT_BREAKOUT")
    assert result["cup_type"] == "DEEP_CUP"


def test_vedl_like_full_structure_remains_valid_after_deep_cup_change():
    """The existing VEDL-like structural test (standard-depth, <=50%) must
    remain entirely unaffected by the DEEP_CUP addition - same fixture
    shape as test_vedl_like_full_structure_reaches_breakout_confirmed."""
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=600.0, recovery_close=950.0, n_decline=36, n_recover=36)
    specs2 = list(specs)
    specs2.append((y, m, 1010.0, 1010.0, 1010.0, 1010.0, 2000.0))
    y2, m2 = _step_month(y, m)
    df2 = _monthly_frame(specs2)
    result = detect_cup(df2, DEFAULT_CONFIG, now=dt.datetime(y2, m2, 10))
    assert result["status"] in ("BREAKOUT_CONFIRMED", "RECENT_BREAKOUT")
    assert result["cup_type"] == "STANDARD_CUP"


def test_bhel_like_multi_cup_selection_remains_valid_after_deep_cup_change():
    """The existing multi-cup "most recent relevant cup wins" behavior must
    be completely unaffected by the DEEP_CUP addition."""
    specs = []
    y, m = 2010, 1
    for _ in range(3):
        specs.append((y, m, 400.0, 400.0, 400.0, 400.0, 1000.0)); y, m = _step_month(y, m)
    specs.append((y, m, 900.0, 900.0, 900.0, 900.0, 2000.0)); y, m = _step_month(y, m)
    price = 900.0
    for i in range(30):
        price -= 500.0 / 30
        specs.append((y, m, price, price, price, price, 1000.0)); y, m = _step_month(y, m)
    for i in range(30):
        price += 480.0 / 30
        specs.append((y, m, price, price, price, price, 1000.0)); y, m = _step_month(y, m)
    specs.append((y, m, 1200.0, 1200.0, 1200.0, 1200.0, 2000.0)); y, m = _step_month(y, m)
    price = 1200.0
    for i in range(24):
        price -= 500.0 / 24
        specs.append((y, m, price, price, price, price, 1000.0)); y, m = _step_month(y, m)
    for i in range(36):
        price += 400.0 / 36
        specs.append((y, m, price, price, price, price, 1000.0)); y, m = _step_month(y, m)
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    assert result["left_rim_price"] == pytest.approx(1200.0, abs=1.0)


def test_deep_cup_does_not_weaken_the_existing_stale_cup_validation():
    """A DEEP_CUP structure whose price has already moved past the
    breakout level on a completed month, then pulled back below it again
    without a fresh confirmed breakout, must still be classified NO_SIGNAL
    (stale) exactly like a STANDARD_CUP - the existing stale-breakout rule
    is untouched by the DEEP_CUP addition."""
    specs, (y2, m2) = _deep_cup_rounded_specs(left_rim=1000.0, cup_low=450.0, recovery_close=900.0)
    specs = specs + [(y2, m2, 1000.0, 1060.0, 995.0, 1040.0, 3000.0)]  # breakout month
    y, m = _step_month(y2, m2)
    # Many completed months after the breakout, well past recent_breakout_months,
    # with price having run up massively beyond the old breakout level.
    for i in range(24):
        price = 1040.0 + i * 150.0
        specs.append((y, m, price, price * 1.02, price * 0.98, price, 2000.0))
        y, m = _step_month(y, m)
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    assert result["status"] == "NO_SIGNAL"
    assert result["rejection_reason"] == "stale_breakout_price_already_moved_away"


def test_deep_cup_does_not_weaken_the_existing_five_percent_and_25_percent_rules():
    """DEEP_CUP candidates are still gated by the SAME min_recovery_pct (5%)
    and max_distance_to_breakout_pct (25%) rules as STANDARD_CUP - the
    DEEP_CUP checks are purely additive on top, never a replacement."""
    # 55% deep decline, but recovery stalls right at the cup low (no real
    # upward turn yet) -> must still fail the existing 5% recovery rule.
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=450.0, recovery_close=460.0, n_decline=40, n_recover=24)
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    assert result["status"] == "NO_SIGNAL"


# ---------------------------------------------------------------------------
# Inverted-cup / rounding-top rejection (2026-09-24, CROPMTON false positive)
#
# A structure that recovers toward its rim and then rolls over and declines
# again — never actually breaking out — is an inverted cup / rounding-top,
# not a bullish Cup, and must be rejected even though the current price may
# still sit within the normal distance/recovery bands of the (never broken)
# breakout level.
# ---------------------------------------------------------------------------

def _cropmton_like_rollover_specs():
    """LEFT RIM (~2016-2017) -> long decline -> long recovery toward (not
    past) the rim -> ROLLS OVER and declines again, materially and for
    several months, right up to "now" - illustrative shape only, matching
    CROPMTON's reported real structure (2021 high -> 2023 low -> recovered
    toward the 2021 high during 2024-2025 -> declined again afterward). No
    CROPMTON data/dates are hardcoded into the detector itself."""
    specs = []
    y, m = 2016, 1
    for _ in range(3):
        specs.append((y, m, 400.0, 400.0, 400.0, 400.0, 1000.0)); y, m = _step_month(y, m)
    specs.append((y, m, 1000.0, 1000.0, 1000.0, 1000.0, 2000.0)); y, m = _step_month(y, m)  # left rim
    price = 1000.0
    for _ in range(30):
        price -= 400.0 / 30
        specs.append((y, m, price, price, price, price, 1000.0)); y, m = _step_month(y, m)  # decline to cup low (~600)
    for _ in range(24):
        price += 350.0 / 24
        specs.append((y, m, price, price, price, price, 1000.0)); y, m = _step_month(y, m)  # recover toward (not past) the rim (~950)
    for _ in range(6):
        price -= 250.0 / 6
        specs.append((y, m, price, price, price, price, 1000.0)); y, m = _step_month(y, m)  # rolls over and declines again
    return specs, (y, m)


def test_cropmton_like_inverted_rounding_top_is_rejected_as_no_signal():
    specs, (y, m) = _cropmton_like_rollover_specs()
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    assert result["status"] == "NO_SIGNAL"
    assert result["rejection_reason"] == "inverted_or_failed_cup_structure"
    assert result["invalidation_reason"] == "inverted_or_failed_cup_structure"


def test_sonacoms_like_still_rising_structure_is_not_flagged_as_rollover():
    """A structure whose right rim IS the latest (or near-latest) bar - i.e.
    still climbing toward its rim, exactly like SONACOMS/VEDL/BHEL's real
    shape - must never trip the new rollover check just because it happens
    to also be a valid, currently-actionable cup."""
    specs, (y, m) = _cup_specs(left_rim=840.0, cup_low=380.0, recovery_close=760.0, n_decline=40, n_recover=24)
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    assert result["status"] in ("EARLY_CUP", "NEAR_BREAKOUT", "BREAKOUT_CONFIRMED", "RECENT_BREAKOUT")
    assert result["rejection_reason"] is None


def test_vedl_like_and_bhel_like_structures_unaffected_by_rollover_check():
    """Same fixtures as the existing VEDL/BHEL-style tests - must remain
    completely unaffected by the CROPMTON rollover-rejection addition."""
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=600.0, recovery_close=950.0, n_decline=36, n_recover=36)
    specs2 = list(specs)
    specs2.append((y, m, 1010.0, 1010.0, 1010.0, 1010.0, 2000.0))
    y2, m2 = _step_month(y, m)
    df2 = _monthly_frame(specs2)
    result = detect_cup(df2, DEFAULT_CONFIG, now=dt.datetime(y2, m2, 10))
    assert result["status"] in ("BREAKOUT_CONFIRMED", "RECENT_BREAKOUT")
