"""
NSE equity market-hours state, Asia/Kolkata — used only by the live
market-data engine (backend/live/*) to decide when tick processing counts
as a normal live session vs. pre/after market. Deliberately separate from
any strategy's own date/time logic; this never changes historical-scan
behavior.
"""
from __future__ import annotations

import datetime as dt
from typing import Literal
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

MarketState = Literal["PRE_MARKET", "MARKET_OPEN", "MARKET_CLOSED"]

MARKET_OPEN_TIME = dt.time(9, 15)
MARKET_CLOSE_TIME = dt.time(15, 30)


def market_state(now: dt.datetime | None = None) -> MarketState:
    """
    now: any timezone-aware or naive datetime (naive is treated as already
    IST — every caller in this module passes IST). Weekends and the
    holiday calendar (is_nse_holiday) both collapse to MARKET_CLOSED; this
    function does NOT itself know the NSE holiday list (that lives in
    is_nse_holiday below, kept separate and small on purpose).
    """
    if now is None:
        now = dt.datetime.now(IST)
    if now.tzinfo is not None:
        now = now.astimezone(IST)
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return "MARKET_CLOSED"
    t = now.time()
    if t < MARKET_OPEN_TIME:
        return "PRE_MARKET"
    if t >= MARKET_CLOSE_TIME:
        return "MARKET_CLOSED"
    return "MARKET_OPEN"


def is_trading_day(date: dt.date, holidays: frozenset[dt.date] = frozenset()) -> bool:
    """Weekday AND not in the given NSE holiday set. `holidays` is injected
    (never hardcoded here) — see backend/config/nse_holidays.py for the
    actual calendar, kept as plain data so it can be updated yearly without
    touching this logic."""
    return date.weekday() < 5 and date not in holidays
