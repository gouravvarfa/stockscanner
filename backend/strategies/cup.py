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


def _classify_deep_cup(
    monthly: pd.DataFrame, cup_low_idx: int, b_idx: int, cup_low_price: float, recovery_range: float, config: CupConfig,
) -> tuple[bool, str | None, int, int]:
    """
    Distinguishes a genuine DEEP (50-60% depth) rounded cup from a
    V-SHAPED crash-and-bounce (2026-09-24, SONACOMS: depth 54.8%,
    rejected by the flat 50% cap despite a real ~14-month base before its
    final breakout thrust). Three deterministic, symmetric checks — ALL
    must pass:

      1. bottom_duration_months: consecutive completed months, starting at
         the cup low, whose CLOSE stays within deep_cup_bottom_band_pct of
         the cup low price — a real base, not one isolated low candle.
      2. recovery_duration_months (cup low -> now) >=
         deep_cup_min_recovery_months — the climb itself took real time.
      3. No single month's close-to-close move exceeds
         deep_cup_max_single_month_share_pct of the ENTIRE recovery range
         (left rim - cup low) — a legitimate final breakout thrust is
         normal and allowed (SONACOMS' own last month was ~34%), but one
         month dominating the *majority* of the whole recovery is exactly
         the V-shape this is meant to exclude.

    Returns (is_deep_cup, rejection_reason, bottom_duration_months,
    recovery_duration_months) — the two duration values are always
    returned (for diagnostics) even when rejected.
    """
    band_price = cup_low_price * (1 + config.deep_cup_bottom_band_pct / 100.0)
    closes = monthly["close"]
    bottom_duration = 0
    for i in range(cup_low_idx, b_idx + 1):
        if float(closes.iloc[i]) <= band_price:
            bottom_duration += 1
        else:
            break

    recovery_duration = b_idx - cup_low_idx

    max_single_month_share = 0.0
    if recovery_range > 0:
        for i in range(cup_low_idx + 1, b_idx + 1):
            move = abs(float(closes.iloc[i]) - float(closes.iloc[i - 1]))
            max_single_month_share = max(max_single_month_share, move / recovery_range * 100.0)

    if bottom_duration < config.deep_cup_min_bottom_months:
        return False, "insufficient_bottom_duration", bottom_duration, recovery_duration
    if recovery_duration < config.deep_cup_min_recovery_months:
        return False, "recovery_too_short", bottom_duration, recovery_duration
    if max_single_month_share > config.deep_cup_max_single_month_share_pct:
        return False, "v_shaped_recovery_too_sharp", bottom_duration, recovery_duration
    return True, None, bottom_duration, recovery_duration


def _find_cup_structure(monthly: pd.DataFrame, config: CupConfig) -> tuple[dict[str, Any] | None, str | None]:
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

    # Recently-listed stocks may not HAVE min_cup_months of total history at
    # all (SONACOMS live example, 2026-09-24: ~5.25y total listed history,
    # so the strict 60-month room requirement left ~zero valid candidate
    # window even though a real multi-year structure is visible on the
    # chart). When total history is already short, require a
    # history-proportional room instead — still most of what's available,
    # never below short_history_min_cup_months, and NEVER larger than
    # min_cup_months, so a stock with genuinely 5+ years available is
    # completely unaffected by this.
    effective_min_cup_months = min(
        config.min_cup_months,
        max(config.short_history_min_cup_months, int(n * config.short_history_ratio)),
    )

    swing_highs = [p.index for p in find_swing_points(monthly["high"], monthly["low"], 2) if p.kind == "high"]
    candidate_idxs = [i for i in swing_highs if i <= b_idx - effective_min_cup_months]
    if not candidate_idxs:
        return None, None

    best: dict[str, Any] | None = None
    best_distance = None
    last_rejection_reason: str | None = None
    for left_rim_idx in candidate_idxs:
        left_rim_price = float(highs.iloc[left_rim_idx])
        if left_rim_price <= 0:
            continue
        after = lows.iloc[left_rim_idx + 1 :]
        if after.empty:
            continue
        cup_low_idx = left_rim_idx + 1 + int(after.values.argmin())
        cup_low_price = float(lows.iloc[cup_low_idx])
        # DOMINANCE (2026-09-24, live ASIANPAINT false positive): the left
        # rim must actually BE the peak the decline falls from — if a HIGHER
        # high occurs anywhere between it and the cup low, this candidate is
        # just an earlier, lesser pivot that price later exceeded before
        # ever really declining; the genuine rim is that later, higher
        # point (which is itself already a separate swing-high candidate in
        # this same loop). Without this, a small/early local high with a
        # shallow-looking "cup" underneath it could out-rank the real,
        # larger structure purely for being numerically closer to today's
        # price — exactly what produced ASIANPAINT's false positive
        # (rim picked at 2021's ~2873 while price had actually rallied to
        # ~3600 in 2022 before the real decline even started).
        between = highs.iloc[left_rim_idx + 1 : cup_low_idx]
        if not between.empty and float(between.max()) > left_rim_price:
            continue
        depth_pct = (left_rim_price - cup_low_price) / left_rim_price * 100.0
        recovery_range = left_rim_price - cup_low_price
        cup_type = "STANDARD_CUP"
        bottom_duration_months = None
        recovery_duration_months = None
        if config.min_depth_pct <= depth_pct <= config.max_depth_pct:
            cup_type = "STANDARD_CUP"
        elif config.max_depth_pct < depth_pct <= config.deep_cup_max_depth_pct:
            is_deep_cup, reason, bottom_duration_months, recovery_duration_months = _classify_deep_cup(
                monthly, cup_low_idx, b_idx, cup_low_price, recovery_range, config,
            )
            if not is_deep_cup:
                last_rejection_reason = reason
                continue
            cup_type = "DEEP_CUP"
        else:
            last_rejection_reason = "depth_out_of_range"
            continue
        # Upside-only (see min_recovery_pct docstring): the cup low can't be
        # the current bar itself (still making new lows, no recovery leg has
        # even started) and the recovery so far must be genuinely positive —
        # otherwise this is still a downtrend, not a cup that has turned up.
        recovery_pct = (latest_close - cup_low_price) / recovery_range * 100.0 if recovery_range > 0 else 0.0
        if cup_low_idx == b_idx or recovery_pct < config.min_recovery_pct:
            last_rejection_reason = "insufficient_recovery"
            continue
        distance = abs((left_rim_price - latest_close) / left_rim_price * 100.0)
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best = {
                "left_rim_idx": left_rim_idx, "left_rim_date": monthly.index[left_rim_idx], "left_rim_price": left_rim_price,
                "cup_low_idx": cup_low_idx, "cup_low_date": monthly.index[cup_low_idx], "cup_low_price": cup_low_price,
                "depth_pct": depth_pct, "cup_type": cup_type,
                "bottom_duration_months": bottom_duration_months, "recovery_duration_months": recovery_duration_months,
            }
    return best, (None if best is not None else last_rejection_reason)


def _handle_details(monthly: pd.DataFrame, breakout_idx: int, breakout_price: float, config: CupConfig) -> dict[str, Any]:
    """
    Optional/informational only — never gates EARLY_CUP/NEAR_BREAKOUT/
    BREAKOUT_FORMING/BREAKOUT_CONFIRMED (see module docstring). A "handle" is
    a shallow pullback (<= handle_max_retrace_pct off the breakout close)
    within handle_max_months of the breakout, not yet a failed breakout.
    """
    empty = {"status": "NOT_FORMED", "start_date": None, "end_date": None, "low_price": None}
    n = len(monthly)
    since = monthly.iloc[breakout_idx + 1 : n]
    if since.empty or breakout_price <= 0:
        return empty
    min_close = float(since["close"].min())
    pullback_pct = max(0.0, (breakout_price - min_close) / breakout_price * 100.0)
    if pullback_pct <= 0 or pullback_pct > config.handle_max_retrace_pct:
        return empty  # no pullback at all, or too deep to be a shallow handle
    still_developing = len(since) <= config.handle_max_months and float(since["close"].iloc[-1]) < float(since["close"].max())
    return {
        "status": "FORMING" if still_developing else "FORMED",
        "start_date": monthly.index[breakout_idx + 1].isoformat(),
        "end_date": monthly.index[n - 1].isoformat(),
        "low_price": round(float(monthly["low"].iloc[breakout_idx + 1 : n].min()), 2),
    }


def _right_rim(monthly: pd.DataFrame, cup_low_idx: int, b_idx: int) -> tuple[int, float]:
    """
    The RIGHT rim: the highest CLOSE actually reached during the recovery so
    far (cup_low -> latest completed bar, inclusive) — real price action
    that has tested the resistance zone, distinct from "current price
    happens to be close" (see CupConfig.max_rim_difference_pct docstring).
    """
    window = monthly["close"].iloc[cup_low_idx + 1 : b_idx + 1]
    if window.empty:
        return b_idx, float(monthly["close"].iloc[b_idx])
    local_idx = int(window.to_numpy().argmax())
    idx = cup_low_idx + 1 + local_idx
    return idx, float(window.iloc[local_idx])


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
        "cup_bottom_date": None, "cup_bottom_price": None,  # alias of cup_low_* (spec naming)
        "right_rim_date": None, "right_rim_price": None,
        "rim_difference_percent": None,
        "cup_depth_percent": None,
        "cup_age_months": None, "cup_age_years": None,
        "candidate_age_months": None,  # alias of cup_age_months (spec naming)
        "recovery_percent": None,
        "recovery_from_bottom_percent": None,  # alias of recovery_percent (spec naming)
        "potential_breakout_level": None,
        "breakout_level": None,  # alias of potential_breakout_level (spec naming)
        "latest_monthly_close": None,
        "distance_to_breakout_percent": None,
        "current_distance_to_breakout_percent": None,  # alias (spec naming)
        "breakout_date": None, "breakout_price": None, "breakout_percent": None,
        "breakout_volume": None, "average_monthly_volume": None, "volume_ratio": None,
        "handle_status": "NOT_FORMED",
        "handle_start_date": None, "handle_end_date": None, "handle_low_price": None,
        "history_years_available": None,
        "invalidation_reason": "insufficient_history",
        "cup_type": None, "bottom_duration_months": None, "recovery_duration_months": None,
        "rejection_reason": "insufficient_history",  # alias of invalidation_reason (spec naming)
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

    structure, structure_rejection_reason = _find_cup_structure(monthly, config)
    if structure is None:
        result["status"] = STATUS_NO_SIGNAL
        result["invalidation_reason"] = structure_rejection_reason or "no_valid_cup_structure_found"
        result["rejection_reason"] = result["invalidation_reason"]
        return result

    left_rim_price = structure["left_rim_price"]
    cup_low_price = structure["cup_low_price"]
    cup_low_idx = structure["cup_low_idx"]
    left_rim_idx = structure["left_rim_idx"]
    breakout_level = left_rim_price  # the validated resistance IS the left rim — no arbitrary percentage

    recovery_range = left_rim_price - cup_low_price
    recovery_pct = ((latest_close - cup_low_price) / recovery_range * 100.0) if recovery_range > 0 else 0.0

    right_rim_idx, right_rim_price = _right_rim(monthly, cup_low_idx, b_idx)
    rim_difference_pct = (left_rim_price - right_rim_price) / left_rim_price * 100.0 if left_rim_price > 0 else 0.0

    cup_age_months = b_idx - left_rim_idx
    result.update({
        "left_rim_date": structure["left_rim_date"].isoformat(),
        "left_rim_price": left_rim_price,
        "cup_low_date": structure["cup_low_date"].isoformat(),
        "cup_low_price": cup_low_price,
        "cup_bottom_date": structure["cup_low_date"].isoformat(),
        "cup_bottom_price": cup_low_price,
        "right_rim_date": monthly.index[right_rim_idx].isoformat(),
        "right_rim_price": round(right_rim_price, 2),
        "rim_difference_percent": round(rim_difference_pct, 2),
        "cup_depth_percent": round(structure["depth_pct"], 2),
        "cup_age_months": cup_age_months,
        "cup_age_years": round(cup_age_months / 12.0, 2),
        "candidate_age_months": cup_age_months,
        "recovery_percent": round(recovery_pct, 2),
        "recovery_from_bottom_percent": round(recovery_pct, 2),
        "potential_breakout_level": breakout_level,
        "breakout_level": breakout_level,
        "invalidation_reason": None,
        "rejection_reason": None,
        "cup_type": structure["cup_type"],
        "bottom_duration_months": structure["bottom_duration_months"],
        "recovery_duration_months": structure["recovery_duration_months"],
    })

    distance_pct = (breakout_level - latest_close) / breakout_level * 100.0
    result["distance_to_breakout_percent"] = round(distance_pct, 2)
    result["current_distance_to_breakout_percent"] = round(distance_pct, 2)

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
        handle = _handle_details(monthly, breakout_idx, breakout_price, config)
        result.update({
            "handle_status": handle["status"],
            "handle_start_date": handle["start_date"],
            "handle_end_date": handle["end_date"],
            "handle_low_price": handle["low_price"],
        })

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
            result["invalidation_reason"] = "stale_breakout_price_already_moved_away"
            result["rejection_reason"] = result["invalidation_reason"]
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

    # Right rim never actually got close to the left rim (see
    # CupConfig.max_rim_difference_pct docstring) — additive strictness on
    # top of (never a replacement for) the distance/recovery filters below.
    if rim_difference_pct > config.max_rim_difference_pct:
        result["status"] = STATUS_NO_SIGNAL
        result["invalidation_reason"] = "rim_mismatch_too_large"
        result["rejection_reason"] = result["invalidation_reason"]
        return result

    if latest_close < breakout_level and distance_pct <= config.near_breakout_pct:
        result["status"] = STATUS_NEAR_BREAKOUT
        return result

    # Still too far from its own resistance to count as an actionable cup
    # yet (still mostly in the decline leg, not a recovering "cup" shape) —
    # see max_distance_to_breakout_pct's docstring in cup_config.py.
    if distance_pct > config.max_distance_to_breakout_pct:
        result["status"] = STATUS_NO_SIGNAL
        result["invalidation_reason"] = "too_far_from_breakout_level"
        result["rejection_reason"] = result["invalidation_reason"]
        return result

    result["status"] = STATUS_EARLY_CUP
    return result
