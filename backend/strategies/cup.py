"""
Cup Breakout — a standalone, long-term MONTHLY pattern detector. Completely
independent of the existing strategy pipeline (System One/GFS/Advanced
GFS/PRD/NRD/Value Buy): different data depth (~10 years vs ~4.1 years),
different timeframe basis (monthly-only, never daily/weekly), different
config (backend/config/cup_config.py), and never imported by
backend/strategies/runner.py or backend/services/scan_service.py's existing
per-stock evaluation. See backend/services/cup_scan_service.py for the
separate scan pipeline that calls this module.

STRUCTURE:
  LEFT RIM (major monthly resistance / swing high)
      -> LONG DECLINE -> CUP LOW (major monthly swing low after the rim)
      -> RECOVERY toward the rim
      -> BREAKOUT ZONE / BREAKOUT

A Cup does NOT need to be finished (right rim / handle) to qualify — see
STATUS below. No lookahead: every field is derived only from COMPLETED
monthly candles (the in-progress current month is excluded by
backend/indicators/resample.py's to_monthly(), which this module reuses
unmodified) plus, for BREAKOUT_FORMING only, the raw still-forming daily
bars of the current calendar month (informational only, never used to set
BREAKOUT_CONFIRMED).
"""
from __future__ import annotations

import datetime as dt
from typing import Any

import pandas as pd

from backend.config.cup_config import CupConfig
from backend.divergence.swing import find_swing_points
from backend.indicators.resample import to_monthly

STATUS_EARLY_CUP = "EARLY_CUP"
STATUS_NEAR_BREAKOUT = "NEAR_BREAKOUT"
STATUS_BREAKOUT_FORMING = "BREAKOUT_FORMING"
STATUS_BREAKOUT_CONFIRMED = "BREAKOUT_CONFIRMED"
STATUS_RECENT_BREAKOUT = "RECENT_BREAKOUT"
STATUS_NO_SIGNAL = "NO_SIGNAL"
STATUS_INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"

# Statuses considered "qualifying" results (visible in the Cup Breakout scan
# results / partial stream) — NO_SIGNAL and INSUFFICIENT_HISTORY are not.
QUALIFYING_STATUSES = {
    STATUS_EARLY_CUP, STATUS_NEAR_BREAKOUT, STATUS_BREAKOUT_FORMING,
    STATUS_BREAKOUT_CONFIRMED, STATUS_RECENT_BREAKOUT,
}


def _months_between(a: pd.Timestamp, b: pd.Timestamp) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)


def _find_cup_structure(monthly: pd.DataFrame, config: CupConfig) -> dict[str, Any] | None:
    """
    A real long-term chart can have MULTIPLE sequential cups (e.g. BHEL:
    a huge older cup, then a second, more recent one formed on its right
    side — per explicit user direction, 2026-09-23, the scanner must
    recognize the CURRENT/most relevant one, not always the single oldest
    or tallest rim). Every genuine swing-high candidate (a real local peak
    — backend/divergence/swing.py's existing fractal pivot detector, same
    one PRD/NRD use, 2 bars either side — not just any bar, so a smooth
    decline/recovery never gets an arbitrary mid-slope point picked as a
    "rim") is evaluated, each still required to leave >= `min_cup_months`
    (5 years, per config) of room before the latest completed bar. Among
    all that produce a valid depth [min_depth_pct, max_depth_pct], the one
    whose current price is CLOSEST to its own breakout level wins — that is
    what "uptrend cup" means here: the most actionable, most-recently-
    relevant structure, not necessarily the biggest one on the chart.
    """
    n = len(monthly)
    b_idx = n - 1  # latest completed monthly bar
    highs = monthly["high"]
    lows = monthly["low"]
    latest_close = float(monthly["close"].iloc[b_idx])

    swing_highs = [p.index for p in find_swing_points(monthly["high"], monthly["low"], 2) if p.kind == "high"]
    candidate_idxs = [i for i in swing_highs if i <= b_idx - config.min_cup_months]
    if not candidate_idxs:
        return None

    best: dict[str, Any] | None = None
    best_distance = None
    for left_rim_idx in candidate_idxs:
        left_rim_price = float(highs.iloc[left_rim_idx])
        if left_rim_price <= 0:
            continue
        after = lows.iloc[left_rim_idx + 1 :]
        if after.empty:
            continue
        cup_low_idx = left_rim_idx + 1 + int(after.values.argmin())
        cup_low_price = float(lows.iloc[cup_low_idx])
        depth_pct = (left_rim_price - cup_low_price) / left_rim_price * 100.0
        if not (config.min_depth_pct <= depth_pct <= config.max_depth_pct):
            continue
        distance = abs((left_rim_price - latest_close) / left_rim_price * 100.0)
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best = {
                "left_rim_idx": left_rim_idx, "left_rim_date": monthly.index[left_rim_idx], "left_rim_price": left_rim_price,
                "cup_low_idx": cup_low_idx, "cup_low_date": monthly.index[cup_low_idx], "cup_low_price": cup_low_price,
                "depth_pct": depth_pct,
            }
    return best


def _handle_status(monthly: pd.DataFrame, breakout_idx: int, breakout_price: float, config: CupConfig) -> str:
    """
    Optional/informational only — never gates EARLY_CUP/NEAR_BREAKOUT/
    BREAKOUT_FORMING/BREAKOUT_CONFIRMED (see module docstring). A "handle" is
    a shallow pullback (<= handle_max_retrace_pct off the breakout close)
    within handle_max_months of the breakout, not yet a failed breakout.
    """
    n = len(monthly)
    since = monthly.iloc[breakout_idx + 1 : n]
    if since.empty or breakout_price <= 0:
        return "NOT_FORMED"
    min_close = float(since["close"].min())
    pullback_pct = max(0.0, (breakout_price - min_close) / breakout_price * 100.0)
    if pullback_pct <= 0 or pullback_pct > config.handle_max_retrace_pct:
        return "NOT_FORMED"  # no pullback at all, or too deep to be a shallow handle
    still_developing = len(since) <= config.handle_max_months and float(since["close"].iloc[-1]) < float(since["close"].max())
    return "FORMING" if still_developing else "FORMED"


def detect_cup(
    daily_ohlcv: pd.DataFrame,
    config: CupConfig,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """
    Pure function: daily OHLCV (DatetimeIndex, open/high/low/close/volume) in
    -> a fully-populated Cup result dict out. `now` is injectable for tests
    (defaults to the real current time) — used only to identify which daily
    bars belong to the still-in-progress current calendar month for the
    informational BREAKOUT_FORMING check; every other field comes only from
    completed monthly candles.
    """
    now = now or dt.datetime.now()
    result: dict[str, Any] = {
        "status": STATUS_INSUFFICIENT_HISTORY,
        "left_rim_date": None, "left_rim_price": None,
        "cup_low_date": None, "cup_low_price": None,
        "cup_depth_percent": None,
        "cup_age_months": None, "cup_age_years": None,
        "recovery_percent": None,
        "potential_breakout_level": None,
        "latest_monthly_close": None,
        "distance_to_breakout_percent": None,
        "breakout_date": None, "breakout_price": None, "breakout_percent": None,
        "breakout_volume": None, "average_monthly_volume": None, "volume_ratio": None,
        "handle_status": "NOT_FORMED",
        "history_years_available": None,
    }

    if daily_ohlcv is None or daily_ohlcv.empty:
        return result

    monthly = to_monthly(daily_ohlcv)
    n = len(monthly)
    if n:
        span_days = (daily_ohlcv.index.max() - daily_ohlcv.index.min()).days
        result["history_years_available"] = round(span_days / 365.25, 2)

    if n < max(6, config.min_cup_months + 1):
        return result  # INSUFFICIENT_HISTORY — not enough completed monthly bars to even attempt a cup

    b_idx = n - 1
    latest_close = float(monthly["close"].iloc[b_idx])
    result["latest_monthly_close"] = latest_close

    structure = _find_cup_structure(monthly, config)
    if structure is None:
        result["status"] = STATUS_NO_SIGNAL
        return result

    left_rim_price = structure["left_rim_price"]
    cup_low_price = structure["cup_low_price"]
    cup_low_idx = structure["cup_low_idx"]
    breakout_level = left_rim_price  # the validated resistance IS the left rim — no arbitrary percentage

    recovery_range = left_rim_price - cup_low_price
    recovery_pct = ((latest_close - cup_low_price) / recovery_range * 100.0) if recovery_range > 0 else 0.0

    result.update({
        "left_rim_date": structure["left_rim_date"].isoformat(),
        "left_rim_price": left_rim_price,
        "cup_low_date": structure["cup_low_date"].isoformat(),
        "cup_low_price": cup_low_price,
        "cup_depth_percent": round(structure["depth_pct"], 2),
        "cup_age_months": b_idx - structure["left_rim_idx"],
        "cup_age_years": round((b_idx - structure["left_rim_idx"]) / 12.0, 2),
        "recovery_percent": round(recovery_pct, 2),
        "potential_breakout_level": breakout_level,
    })

    distance_pct = (breakout_level - latest_close) / breakout_level * 100.0
    result["distance_to_breakout_percent"] = round(distance_pct, 2)

    # First COMPLETED month, after the cup low, whose close crossed above the
    # breakout level — never uses the in-progress current month.
    closes_after_low = monthly["close"].iloc[cup_low_idx + 1 :]
    breakout_idx: int | None = None
    for offset, close in enumerate(closes_after_low):
        if close > breakout_level:
            breakout_idx = cup_low_idx + 1 + offset
            break

    if breakout_idx is not None:
        months_since = b_idx - breakout_idx
        breakout_price = float(monthly["close"].iloc[breakout_idx])
        breakout_pct = (breakout_price - breakout_level) / breakout_level * 100.0
        avg_vol = float(monthly["volume"].iloc[max(0, breakout_idx - 12) : breakout_idx].mean()) if breakout_idx > 0 else None
        breakout_vol = float(monthly["volume"].iloc[breakout_idx]) if "volume" in monthly.columns else None
        result.update({
            "breakout_date": monthly.index[breakout_idx].isoformat(),
            "breakout_price": breakout_price,
            "breakout_percent": round(breakout_pct, 2),
            "breakout_volume": breakout_vol,
            "average_monthly_volume": avg_vol,
            "volume_ratio": round(breakout_vol / avg_vol, 2) if avg_vol else None,
        })
        result["handle_status"] = _handle_status(monthly, breakout_idx, breakout_price, config)

        if months_since == 0:
            result["status"] = STATUS_BREAKOUT_CONFIRMED
            return result
        if 0 < months_since <= config.recent_breakout_months:
            result["status"] = STATUS_RECENT_BREAKOUT
            return result
        # A stale (>recent_breakout_months old) breakout. If price is still
        # ABOVE that old level, this setup already played out long ago —
        # the old rim is no longer meaningful resistance, so it must NOT be
        # reported as EARLY_CUP/NEAR_BREAKOUT against it (real bug, found
        # live on ACE 2026-09-23: a breakout from ~4 years ago with price
        # since running 4x past it was showing "EARLY_CUP" with a nonsense
        # -308% distance/965% recovery, because the code kept evaluating
        # everything below against the original, long-since-irrelevant
        # left rim). Only a genuine PULLBACK — price back at/below the old
        # level, actually re-testing it — is still actionable, so THAT case
        # alone is allowed to fall through to the NEAR_BREAKOUT/EARLY_CUP
        # checks below.
        if latest_close > breakout_level:
            result["status"] = STATUS_NO_SIGNAL
            return result

    # BREAKOUT_FORMING: today's still-forming month is already testing/above
    # the level, but no COMPLETED month has confirmed it yet. Informational
    # only — never sets BREAKOUT_CONFIRMED (see module docstring / no-lookahead).
    current_month_daily = daily_ohlcv[
        (daily_ohlcv.index.year == now.year) & (daily_ohlcv.index.month == now.month)
    ]
    if not current_month_daily.empty:
        live_high = float(current_month_daily["high"].max())
        if live_high >= breakout_level and latest_close <= breakout_level:
            result["status"] = STATUS_BREAKOUT_FORMING
            return result

    if latest_close < breakout_level and distance_pct <= config.near_breakout_pct:
        result["status"] = STATUS_NEAR_BREAKOUT
        return result

    # Still too far from its own resistance to count as an actionable cup
    # yet (still mostly in the decline leg, not a recovering "cup" shape) —
    # see max_distance_to_breakout_pct's docstring in cup_config.py.
    if distance_pct > config.max_distance_to_breakout_pct:
        result["status"] = STATUS_NO_SIGNAL
        return result

    result["status"] = STATUS_EARLY_CUP
    return result
