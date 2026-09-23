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

    # ---- Breakout classification -----------------------------------------
    near_breakout_pct: float = 10.0
    recent_breakout_months: int = 3

    # ---- Handle (optional, informational only — see backend/strategies/cup.py)
    handle_max_months: int = 3
    handle_max_retrace_pct: float = 15.0


DEFAULT_CUP_CONFIG = CupConfig()
