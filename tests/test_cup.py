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


def _cup_specs(left_rim=1000.0, cup_low=600.0, recovery_close=900.0, n_decline=12, n_recover=12, n_lead=0):
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
    recover_step = (recovery_close - cup_low) / n_recover
    price = cup_low
    for i in range(n_recover):
        price += recover_step
        specs.append((y, m, price, price, price, price, 1000.0)); m += 1
        if m > 12: m, y = 1, y + 1
    last_year_month = (y, m)
    return specs, last_year_month


def test_valid_developing_cup_is_early_cup_or_near_breakout():
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=600.0, recovery_close=750.0)  # recovery ~37.5%, not near
    df = _monthly_frame(specs)
    now = dt.datetime(y, m, 10)
    result = detect_cup(df, DEFAULT_CONFIG, now=now)
    assert result["status"] == "EARLY_CUP"
    assert result["cup_depth_percent"] == pytest.approx(40.0, abs=0.5)
    assert result["left_rim_price"] == pytest.approx(1000.0)
    assert result["cup_low_price"] == pytest.approx(600.0)


def test_cup_without_completed_right_rim_still_qualifies():
    # recovery stops well short of the rim — right side never "completes" —
    # must still qualify (EARLY_CUP), per spec section 3/13.
    specs, (y, m) = _cup_specs(left_rim=1000.0, cup_low=600.0, recovery_close=650.0)
    df = _monthly_frame(specs)
    result = detect_cup(df, DEFAULT_CONFIG, now=dt.datetime(y, m, 10))
    assert result["status"] in ("EARLY_CUP", "NEAR_BREAKOUT")
    assert result["recovery_percent"] < 20


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
