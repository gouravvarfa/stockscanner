from __future__ import annotations

import datetime as dt

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def to_ist(moment: dt.datetime) -> dt.datetime:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.timezone.utc)
    return moment.astimezone(IST)


def worksheet_name(moment: dt.datetime, attempt: int = 0) -> str:
    """DD-MMM-YYYY_HH-mm in India time, e.g. 20-Sep-2026_16-30. Locale-free
    month names (never strftime %b). `attempt` > 0 appends _2, _3 ... only
    when that exact name is already taken by ANOTHER scan."""
    t = to_ist(moment)
    base = f"{t.day:02d}-{_MONTHS[t.month - 1]}-{t.year}_{t.hour:02d}-{t.minute:02d}"
    return base if attempt == 0 else f"{base}_{attempt + 1}"
