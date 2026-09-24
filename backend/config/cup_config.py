"""
Dedicated configuration for the Cup Breakout scanner (backend/strategies/cup.py,
backend/services/cup_scan_service.py, backend/providers/cup_history.py).

Deliberately SEPARATE from multi_strategy_config.py (PRD/NRD/GFS/Advanced
GFS/Value Buy) and from MONTHLY_RSI_LOOKBACK_DAYS (market_data_router.py) —
Cup Breakout needs ~10 YEARS of monthly structure, a completely different
history depth than any existing strategy, and must never influence or be
influenced by their RSI/divergence calculations.
"""
from __future__ import annotations

from pydantic import BaseModel


class CupConfig(BaseModel):
    # ---- History depth --------------------------------------------------
    # ~10 years of daily candles, fetched in chunks (Angel One's ONE_DAY
    # candle endpoint was verified — read-only, 2026-09-23 — to reliably
    # return ~500 candles (~2 years) per request without truncating actual
    # history; BHEL data was confirmed available back to at least
    # 2005-01-03). CUP_CHUNK_DELAY_SECONDS keeps chunked requests from
    # tripping Angel One's rate limiter (observed live: HTTP 403 on rapid
    # back-to-back chunk requests, gone entirely once spaced out).
    history_years: int = 10
    chunk_years: float = 2.0
    chunk_delay_seconds: float = 3.0

    # ---- Cup structure ----------------------------------------------------
    min_depth_pct: float = 12.0
    max_depth_pct: float = 50.0
    # A cup must span at least this many completed monthly candles between
    # its left rim and the latest completed month — per explicit user
    # direction (2026-09-23): this is a LONG-TERM cup scanner, so a cup
    # under 5 years is never reported (longer is fine/better, no upper cap).
    min_cup_months: int = 60
    # Recently-listed stocks (e.g. a 2021 IPO) may simply not HAVE 5 years
    # of history at all yet — per explicit user direction (2026-09-24,
    # SONACOMS example): rather than reject them outright, a stock whose
    # TOTAL available history is short uses a reduced, history-proportional
    # minimum instead of the full 60 months — still requiring most of
    # whatever history exists (never shorter than
    # short_history_min_cup_months), so this is a relaxation for limited
    # history, never a general weakening of the 5-year rule for stocks that
    # actually have 5+ years available.
    short_history_min_cup_months: int = 24
    short_history_ratio: float = 0.65

    # ---- Breakout classification -----------------------------------------
    near_breakout_pct: float = 10.0
    recent_breakout_months: int = 3
    # A valid-depth structure whose price is still farther than this from
    # its own breakout level is NOT reported at all (NO_SIGNAL), not even
    # as EARLY_CUP — per explicit user direction (2026-09-23, ACC example):
    # a stock still 48% below its rim, with ~2% recovery, hasn't actually
    # started forming a cup shape yet; it's still in the decline leg. Only
    # a structure that has meaningfully turned and is within reach of its
    # own resistance counts as an actionable (even if early) cup.
    max_distance_to_breakout_pct: float = 25.0
    # An UPSIDE-only scanner (explicit user direction, 2026-09-24: "upside
    # wale cup hi chahiye... downtrend wale nahi chahiye") — a structure
    # whose cup low IS the latest completed month (no recovery candle yet:
    # the stock is still making new lows, not turning up) or whose recovery
    # is not yet meaningfully positive is still in its decline leg, not an
    # actual cup. Gated out as NO_SIGNAL, same as too-shallow/too-deep.
    min_recovery_pct: float = 5.0

    # ---- DEEP CUP (2026-09-24, SONACOMS structural investigation) --------
    # depth > max_depth_pct is normally rejected outright — a 55% crash is
    # NOT automatically a cup just because it's deep; it could just as
    # easily be a V-shaped crash-and-bounce, which is structurally NOT a
    # cup. A deep decline only qualifies (as cup_type=DEEP_CUP, never
    # STANDARD_CUP) when it ALSO has: a genuine multi-month base at the
    # bottom (not one sharp low), a recovery that has taken real time (not
    # an instant spike), and no single month's move accounting for most of
    # the whole recovery. See _classify_deep_cup() in strategies/cup.py for
    # the exact deterministic check.
    deep_cup_max_depth_pct: float = 60.0
    deep_cup_min_bottom_months: int = 4
    deep_cup_min_recovery_months: int = 8
    deep_cup_bottom_band_pct: float = 60.0
    deep_cup_max_single_month_share_pct: float = 40.0

    # ---- Right rim (2026-09-24, VEDL/BHEL structural reference) ----------
    # The RIGHT rim is the highest CLOSE actually reached during the
    # recovery so far (cup_low -> now) — real price action that has tested
    # the resistance zone, not just "current price happens to be close".
    # A candidate whose best-ever recovery point never got within this much
    # of the left rim is rejected (NO_SIGNAL) even if it separately passes
    # max_distance_to_breakout_pct on the current bar alone — additive
    # strictness, never looser than the existing distance/recovery filters.
    max_rim_difference_pct: float = 20.0

    # ---- Handle (optional, informational only — see backend/strategies/cup.py)
    handle_max_months: int = 3
    handle_max_retrace_pct: float = 15.0


DEFAULT_CUP_CONFIG = CupConfig()
