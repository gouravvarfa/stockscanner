"""
NSE equity trading-holiday calendar — plain data, used only by
backend/live/market_hours.py's is_trading_day(). Kept separate from that
logic so the calendar can be updated yearly without touching any code.

NOTE: this list must be reviewed/updated at the start of each calendar
year from NSE's official published holiday calendar
(https://www.nseindia.com/resources/exchange-communication-holidays).
Not exhaustive by design — an unlisted actual holiday only means
is_trading_day() returns True for that one day; the live engine still
never fabricates data (see market_data_service.py), so this only affects
the MARKET_CLOSED banner text, never Angel One data itself.
"""
from __future__ import annotations

import datetime as dt

NSE_HOLIDAYS_2026: frozenset[dt.date] = frozenset({
    dt.date(2026, 1, 26),   # Republic Day
    dt.date(2026, 3, 4),    # Holi
    dt.date(2026, 3, 21),   # Id-Ul-Fitr
    dt.date(2026, 4, 3),    # Good Friday
    dt.date(2026, 4, 14),   # Dr. Ambedkar Jayanti
    dt.date(2026, 5, 1),    # Maharashtra Day
    dt.date(2026, 8, 15),   # Independence Day
    dt.date(2026, 10, 2),   # Gandhi Jayanti
    dt.date(2026, 10, 20),  # Diwali (Laxmi Pujan)
    dt.date(2026, 11, 24),  # Guru Nanak Jayanti
    dt.date(2026, 12, 25),  # Christmas
})

ALL_NSE_HOLIDAYS: frozenset[dt.date] = NSE_HOLIDAYS_2026
